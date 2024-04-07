use bitbuffer::BitRead;
use clap::{ArgAction, Parser};
use indicatif::{ProgressBar, ProgressState, ProgressStyle};
use main_error::MainError;
use std::{fmt::Write, fs, path::PathBuf, str::FromStr, time::Duration};
use tf_demo_parser::demo::{
    header::Header,
    packet::Packet,
    parser::{gamestateanalyser::GameStateAnalyser, DemoHandler, RawPacketStream},
};
use tf_demo_parser::Demo;
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::{
    fmt::writer::MakeWriterExt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter, Layer,
};

#[allow(clippy::struct_excessive_bools)]
#[derive(Parser, Debug)]
#[command(version, about, long_about = None)]
struct Args {
    #[arg(short, long)]
    infile: String,
    #[arg(short, long, default_value = ".")]
    outpath: String,
    #[arg(long, action=ArgAction::SetTrue, default_value_t = false)]
    parse_raw: bool,
    #[arg(long, action=ArgAction::SetTrue, default_value_t = false)]
    dont_parse_gamestate: bool,
}

fn main() -> Result<(), MainError> {
    let _guard = init_tracing();
    let args = Args::parse();
    if let Err(e) = fs::read_dir(&args.outpath) {
        panic!(
            "Error: 'outpath' argument was invalid. Make sure it exists, and is a directory. {e}"
        );
    }

    let file = fs::read(args.infile)?;

    let demo = Demo::new(&file);
    let mut handler = DemoHandler::with_analyser(GameStateAnalyser::new());

    let mut stream = demo.get_stream();
    let header = Header::read(&mut stream).unwrap();
    handler.handle_header(&header);
    let total = header.ticks;

    // A Vector of the raw packets, as these are cloneable and can be serialised later
    let mut packets: Vec<Packet> = Vec::new();
    // A Vector of json-serialised gamestate strings
    let mut game_state: Vec<String> = Vec::new();
    let mut packet_stream: RawPacketStream = RawPacketStream::new(stream);
    let mut current_tick: u32 = 0;

    let bar = ProgressBar::new(total as u64);
    let tick_strs = [
        "⢀⠀", "⡀⠀", "⠄⠀", "⢂⠀", "⡂⠀", "⠅⠀", "⢃⠀", "⡃⠀", "⠍⠀", "⢋⠀", "⡋⠀", "⠍⠁", "⢋⠁", "⡋⠁", "⠍⠉",
        "⠋⠉", "⠋⠉", "⠉⠙", "⠉⠙", "⠉⠩", "⠈⢙", "⠈⡙", "⢈⠩", "⡀⢙", "⠄⡙", "⢂⠩", "⡂⢘", "⠅⡘", "⢃⠨", "⡃⢐",
        "⠍⡐", "⢋⠠", "⡋⢀", "⠍⡁", "⢋⠁", "⡋⠁", "⠍⠉", "⠋⠉", "⠋⠉", "⠉⠙", "⠉⠙", "⠉⠩", "⠈⢙", "⠈⡙", "⠈⠩",
        "⠀⢙", "⠀⡙", "⠀⠩", "⠀⢘", "⠀⡘", "⠀⠨", "⠀⢐", "⠀⡐", "⠀⠠", "⠀⢀", "⠀⡀",
    ];
    let bar_style_template = ProgressStyle::with_template(
        "{spinner:.green} [{elapsed_precise}] [{bar:.green}] {msg} ({eta})",
    )
    .unwrap()
    .with_key("eta", |state: &ProgressState, w: &mut dyn Write| {
        write!(w, "{:.1}s", state.eta().as_secs_f64()).unwrap()
    })
    .progress_chars("█▉▊▋▌▍▎▏  ")
    .tick_strings(&tick_strs);
    bar.set_style(bar_style_template.clone());
    bar.set_message("Parsing demo ticks...");
    bar.enable_steady_tick(Duration::from_millis(25));

    loop {
        match packet_stream.next(&handler.state_handler) {
            Ok(Some(packet)) => {
                if args.parse_raw {
                    packets.push(packet.clone());
                }

                handler
                    .handle_packet(packet)
                    .expect("Couldn't handle packet.");
                if !args.dont_parse_gamestate && handler.server_tick != current_tick {
                    bar.inc(1);

                    // print!("updating gamestate!!! 😂");
                    let output = handler.borrow_output();
                    let output_serialised = serde_json::to_string(output).unwrap();
                    game_state.push(output_serialised);
                }
                current_tick = handler.server_tick.into();
            }
            Ok(None) => break,
            Err(e) => {
                // We want to pull as much data as possible, even if this packet is corrupted
                // Continue the stream and see if we can't recover.
                println!("{:?}", e);
                packet_stream.ended = false;
                packet_stream.incomplete = false;
            }
        }
    }
    bar.finish_with_message("Demo parsed.");

    let output_style_template =
        ProgressStyle::with_template("{spinner:.green} {msg} [{elapsed_precise}]")
            .unwrap()
            .tick_strings(&tick_strs);
    let output_bar = ProgressBar::new_spinner();
    output_bar.set_style(output_style_template);
    output_bar.set_message("Writing output json files...");
    output_bar.enable_steady_tick(Duration::from_millis(33));

    let path: PathBuf =
        PathBuf::from_str(args.outpath.as_str()).expect("Couldn't convert outpath to path");
        bar.println(format!("Preparing to write files to {}", &args.outpath));

    if !args.dont_parse_gamestate {
        let gs_path = path.join("parsed_game_state_evolution.json");
        std::fs::write(&gs_path, serde_json::to_string(&game_state).unwrap())
            .expect("Unable to write file");
        bar.println(format!("Output game state json: {:#?}.", gs_path));
    }

    if args.parse_raw {
        let raw_path = path.join("raw_packets_stream.json");
        std::fs::write(&raw_path, serde_json::to_string(&packets).unwrap())
            .expect("Unable to write file");
        bar.println(format!("Output raw packet stream json: {:#?}.", raw_path));
    }

    output_bar.finish_with_message("Output done.");
    Ok(())
}

fn init_tracing() -> Option<WorkerGuard> {
    if std::env::var("RUST_LOG").is_err() {
        std::env::set_var("RUST_LOG", "info,hyper::proto=warn");
    }

    let subscriber = tracing_subscriber::registry().with(
        tracing_subscriber::fmt::layer()
            .with_writer(std::io::stderr)
            .with_filter(EnvFilter::from_default_env()),
    );

    match std::fs::File::create("./minidemo_parser.log") {
        Ok(latest_log) => {
            let (file_writer, guard) = tracing_appender::non_blocking(latest_log);
            subscriber
                .with(
                    tracing_subscriber::fmt::layer()
                        .with_ansi(false)
                        .with_writer(file_writer.with_max_level(tracing::Level::TRACE)),
                )
                .init();
            Some(guard)
        }
        Err(e) => {
            subscriber.init();
            tracing::error!(
                "Failed to create log file, continuing without persistent logs: {}",
                e
            );
            None
        }
    }
}
