use bitbuffer::BitRead;
use clap::{ArgAction, Parser};
use indicatif::{ProgressBar, ProgressState, ProgressStyle};
use main_error::MainError;
use serde::Serialize;
use std::{fmt::Write, fs::{self, File}, io::BufWriter, path::PathBuf, str::FromStr, time::Duration};
use tf_demo_parser::demo::{
    header::Header,
    parser::{gamestateanalyser::{GameState, GameStateAnalyser}, DemoHandler, RawPacketStream},
};
use tf_demo_parser::Demo;
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::{
    fmt::writer::MakeWriterExt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter, Layer,
};
use rmp_serde::Serializer;

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

    tracing::info!("Reading provided input demo...");
    let file = fs::read(&args.infile)?;

    tracing::info!("Instantiating Demo Handler...");
    let demo = Demo::new(&file);
    let mut handler = DemoHandler::with_analyser(GameStateAnalyser::new());

    tracing::info!("Handling the demo header...");
    let mut stream = demo.get_stream();
    let header = Header::read(&mut stream).unwrap();
    handler.handle_header(&header);
    tracing::info!("Success! Preparing to handle packet stream...");
    let total = header.ticks;

    // A Vector of json-serialised gamestate strings
    let mut packet_stream: RawPacketStream = RawPacketStream::new(stream);
    let mut current_tick: u32 = 0;

    tracing::info!("Generating msgpack serialisers...");
    let demo_name = args.infile.split_once(".dem").unwrap().0;
    let path: PathBuf = PathBuf::from_str(args.outpath.as_str()).expect("Couldn't convert outpath to path");
    let gs_path = path.join(format!("{demo_name}-gsd.msgpack"));
    let raw_path = path.join(format!("{demo_name}-raw.msgpack"));
    

    // GameState Delta output msgpack file
    let gsd_outfile = File::create(gs_path).expect("Couldn't create output file.");
    let gsd_file_bufwriter = BufWriter::new(&gsd_outfile);
    let mut gsd_msgpack_serialiser = Serializer::new(gsd_file_bufwriter);
    tracing::info!("Generated GameStateDelta serialiser with file {:?}.", &gsd_outfile);
    // Raw packets output msgpack file
    let raw_outfile = File::create(&raw_path).expect("Couldn't create output file.");
    let raw_file_bufwriter = BufWriter::new(raw_outfile);
    let mut raw_msgpack_serialiser = Serializer::new(raw_file_bufwriter);
    if args.parse_raw {
        tracing::info!("Generated raw serialiser with file {:?}.", &gsd_outfile);
    } else {
        fs::remove_file(&raw_path).expect("Couldn't delete newly created but unneeded file.");
    }

    tracing::info!("Parsing demo packets...");
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
                    packet.clone().serialize(&mut raw_msgpack_serialiser).expect("Couldn't serialise raw packet");
                }

                handler
                    .handle_packet(packet)
                    .expect("Couldn't handle packet.");

                if !args.dont_parse_gamestate && handler.server_tick != current_tick {
                    bar.inc(1);
                    // print!("updating gamestate!!! 😂");
                    let output: &GameState = handler.borrow_output();
                    output.serialize(&mut gsd_msgpack_serialiser).expect("Couldn't serialise game state delta");
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
    tracing::info!("Demo packet parsing succeeded.");
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
