# Solaris

## Introduction
Solaris is an accurate, stateful solar farm simulator intended for visualizing and testing solar farm behavior over time by using real and geolocated data in tandem with a state-of-the-art physics engine for photovoltaic modules and inverters as is PVLib.

PVLib is used as an "ideal output" baseline, which is then replicated across multiple instances of a custom "Panel" class that serves as a state holder to simulate effects such as dirt accumulation, degradation of output and failure among others over time.

Here is a quick diagram showing the workflow:
![Solaris_Workflow diagram](https://github.com/MewKitBit/Solaris/blob/master/Media/Solaris_Workflow.png)

This stateful component is written in both Python and Rust.
- **Why Python?**: Because it's the language PVLib is written in and I know it well.
- **Why Rust?**: Because I want to learn Rust and porting this is a good first contact.

## Info
This project is powered by the PVLib engine.
![Solaris_Workflow diagram](https://github.com/MewKitBit/Solaris/blob/master/Media/pvlib_powered_logo_horiz.webp)
