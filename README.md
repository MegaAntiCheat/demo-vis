# Demo Vis(ualisation and Extraction) Project

**-- This repo is a mess while it is in early development --**

This is a WIP project (open to contribution from all org members) for extracting useful data from a json-converted demo 
for use in other static analysis projects. This project also serves to develop a deeper understanding of demo internals
and the type and quality of information a player will receive about other in-game clients. 

The project consists of 2 parts

## Pure-Python JSON converter

The pure-python component (found in `./src/`) takes a json-converted demo and extracts relevant data to create several 
useful time-series tables on all in game clients and relevant objects (such as spawned projectiles) for static cheat 
detection and/or analysis

## Rust Demo Converter

The rust component (found in `./rs/`) takes a TF2 `.dem` file and converts it into a JSON for use by the python 
component. This leverages the Rust demos.tf demo parser, found at https://crates.io/crates/tf-demo-parser/0.5.0
and on the demostf Github.