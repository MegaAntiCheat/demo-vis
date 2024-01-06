use bitbuffer::{BitRead, BitReadBuffer, BitReadStream, LittleEndian};
use tf_demo_parser::Demo;
use main_error::MainError;
use tf_demo_parser::demo::{
    header::Header,
    packet::Packet,
    parser::{DemoHandler, RawPacketStream},
};
use std::fs;
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::{
    fmt::writer::MakeWriterExt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter, Layer,
};


fn main() -> Result<(), MainError> {
    let _guard = init_tracing();

    let file = fs::read("demo_to_ingest.dem")?;

    let demo = Demo::new(&file);
    let mut handler = DemoHandler::default();

    let mut stream = demo.get_stream();
    let header = Header::read(&mut stream).unwrap();
    handler.handle_header(&header);
    
    let mut packets: Vec<Packet> = Vec::new();
    let mut packet_stream: RawPacketStream = RawPacketStream::new(stream);
    loop {
        match packet_stream.next(&handler.get_parser_state()) {
            Ok(Some(packet)) =>  {
                packets.push(packet.clone());
                handler.handle_packet(packet).unwrap();
            }
            Ok(None) => break,
            Err(e) => {
                println!("{:?}", e);
                packet_stream.ended = false;
                packet_stream.incomplete = false;
            }

        }
    }

    // while let Ok(Some(packet)) = packet_stream.next(&handler.get_parser_state()) {
    //     packets.push(packet);
    // }

    std::fs::write(
        "./demo_trace.json",
        serde_json::to_string(&packets).unwrap(),
    )
    .expect("Unable to write file");

    println!("Wrote demo json to file.");
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

    match std::fs::File::create("./macclient.log") {
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