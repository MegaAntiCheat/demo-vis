use bitbuffer::{BitRead, BitReadBuffer, BitReadStream, LittleEndian};
use tf_demo_parser::demo::{
    header::Header,
    packet::{self, Packet},
    parser::{DemoHandler, RawPacketStream},
};

const data: &[u8] = include_bytes!("../voteiddemo.dem");

fn main() {
    let mut handler = DemoHandler::default();

    let buffer = BitReadBuffer::new(data, LittleEndian);
    let mut stream = BitReadStream::new(buffer);

    let header = Header::read(&mut stream).unwrap();

    handler.handle_header(&header);

    let mut packets: Vec<Packet> = Vec::new();
    let mut packet_stream: RawPacketStream = RawPacketStream::new(stream);
    while let Ok(Some(packet)) = packet_stream.next(&handler.get_parser_state()) {
        packets.push(packet);
    }

    std::fs::write(
        "./demo_trace.json",
        serde_json::to_string(&packets).unwrap(),
    )
    .expect("Unable to write file");

    println!("Wrote demo json to file.");
}
