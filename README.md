# Zoom spectrum

A live, zoomed-in spectrum viewer for tuning a piano by ear and by eye. It shows the frequency spectrum of the microphone signal in a narrow band around one note, with the long analysis windows needed to separate the individual strings of a unison. Target frequencies can come from plain equal temperament or from a tuning curve calculated by the [Entropy Piano Tuner](https://piano-tuner.org) (EPT) for your own piano.

The idea is an old one: zoom into a frequency range, lengthen the FFT window until the peaks of all strings of one note are visible, and tune each string against a marker at its target frequency.

## Contents

- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Using the app](#using-the-app)
- [How it works](#how-it-works)
- [Getting target frequencies from the Entropy Piano Tuner](#getting-target-frequencies-from-the-entropy-piano-tuner)
- [Configuration constants](#configuration-constants)
- [Known limitations](#known-limitations)
- [Development notes](#development-notes)

## Quick start

- Requirements
  - Python 3 (developed with 3.12 from miniforge on Windows)
  - Packages: numpy, PySide6, pyqtgraph, sounddevice (see `requirements.txt`)
- Install
  - pip: `pip install -r requirements.txt`
  - conda: `conda install numpy pyside6 pyqtgraph python-sounddevice`
- Run with no hardware, using a synthetic three-string signal
  - `python app.py --source synth`
- Run with the microphone and your own tuning curve
  - `python app.py --source mic --targets C:\tuner\mypiano_targets.csv`
  - `go.bat` contains exactly this line
- Run it from the `spectrum` folder (or double-click `go.bat` there), because `app.py` is a relative path
- Use the miniforge prompt (or any Python that has the packages), since `go.bat` calls plain `python`

### Command-line options

- `--source mic|synth`
  - `mic` reads the default input device through sounddevice
  - `synth` generates three slightly detuned strings (-3, 0, +2 cents) with inharmonic partials, so the app can be tested without a microphone
  - default: `synth`
- `--center HZ`
  - starting center frequency, default 440
  - the note dropdown starts on the note nearest to this value
  - with `--source synth` the synthetic strings are generated around this frequency
- `--span CENTS`
  - how far the view extends on each side of the center, in cents, default 50
- `--device NAME_OR_INDEX`
  - input device for `--source mic`; if you have several, `python -m sounddevice` lists them
- `--targets FILE.csv`
  - tuning curve to use for the note list, see [the CSV format](#the-csv-format); without it, 88-key equal temperament with A4 = 440 Hz is used

## Project layout

- `app.py`
  - the GUI (PySide6 and pyqtgraph), the controls, the keyboard handling and the plot
- `core.py`
  - pure numpy and standard-library code with no audio or GUI dependency
  - `band_spectrum`: Hann-windowed FFT cropped to a band
  - `peak_freq`: loudest bin with parabolic interpolation
  - `cents`: frequency ratio to cents
  - `note_name`, `equal_temperament`, `load_targets_csv`: the note list
  - `center_ticks`: x-axis ticks anchored on the center frequency
- `sources.py`
  - `MicSource`: live input into a 16 s ring buffer
  - `SyntheticSource`: the test signal
  - both expose `.fs` and `.read_latest(n)`, so the rest of the app does not care which one it has
- `requirements.txt`: the four packages, unpinned
- `go.bat`: the one-line launcher
- `README.md`: this file

Two helper scripts that produce and check the CSV currently live outside this folder, in `/home/gabi/` on the WSL side. They are described below.

## Using the app

### Controls

- **Window** slider
  - length of the analysed signal, from 0.1 s to 16 s on a logarithmic scale
  - the label next to it shows the length in seconds and the resulting resolution, about 1/T Hz
- **Samples** box
  - the same window length as an exact sample count, from 256 samples up to 16 s
  - typing a number and pressing Enter (or leaving the box) moves the slider to match
  - invalid text reverts to the current value
- **Note** dropdown
  - every key in the loaded tuning curve (for example `A4  440.00 Hz`)
  - it is editable, so you can type a name such as `A4`
  - choosing a note sets the center to that note's frequency and moves the marker lines
- **Center Hz**
  - the center of the view; typing a different value does not move the marker lines until you pick a note again
- **Span ± cents**
  - the view extends this many cents each side of the center, from 1 to 1200 with one decimal

### Keyboard

- Left and Right: previous and next note
- Up and Down: window length plus or minus 1 s (Down is clamped at 256 samples, so from 1 s or less it jumps to the minimum)
- Escape, or a click on the graph or the window background: removes keyboard focus from whichever box has it
- While a text box (Samples, Center, Span, Note) has focus it keeps its own arrow keys, which is why you click the graph first
- An open dropdown list also keeps its arrow keys
- The slider is set not to take focus, so it never captures the arrows

### The plot

- A dashed red line marks the selected note's target frequency
- Ten dimmer dashed lines sit at ±5, ±10, ±15, ±20 and ±25 cents around it (spacing is true cents, not equal Hz)
- The x-axis is in Hz and always has the center frequency exactly in the middle, with a tick labeled at the center
- The y-axis top follows the highest level seen over the last 10 s, so it does not jump with every frame
- The "Peak" readout below the plot is the loudest bin, refined by parabolic interpolation
  - with a unison of several strings it jumps between strings, because it reports only the loudest one

## How it works

- Every 50 ms the app takes the last N samples from the audio source, where N is the window length
- It applies a Hann window and takes an FFT, then keeps only the bins inside the band `center ± h`
- The band
  - `h = center * sinh(span * ln(2) / 1200)`
  - this makes the band symmetric in Hz, so the center sits exactly mid-axis
  - the price is a small asymmetry in cents: at the default 50 cents the edges are about -50.7 and +49.3 cents
  - at the maximum span (1200) the asymmetry is large (110 Hz to 770 Hz around 440 Hz)
- Resolution
  - frequency resolution is about 1/T Hz, set by how long you listen, not by the sample rate and not by the width of the band
  - two strings 0.2 Hz apart need a window of about 5 s or more
  - zero-padding (2x, rounded up to a power of 2) only interpolates the curve between points; it does not separate close peaks
- Sample rate
  - 48 kHz is requested from the microphone (`fs=48000` in `sources.py`)
  - a higher rate would not sharpen the peaks; it would only raise the cost of each FFT
- The center-and-span change redraws at once instead of waiting for the next timer tick, and the x range is set explicitly, to avoid a flicker when the band changes

## Getting target frequencies from the Entropy Piano Tuner

The EPT is a separate C++/Qt project (in this setup, `/mnt/c/tuner/Entropy-Piano-Tuner`). It measures your piano, calculates an entropy-minimizing tuning curve, and saves everything in an `.ept` file. This project reads one number per key from that file.

### Background

- Piano strings are stiff, so their overtones are slightly sharp of exact multiples of the fundamental: f_n is about n * f0 * sqrt(1 + B * n^2), where B is the inharmonicity
- B differs between pianos and between keys, so a good tuning has to be calculated from measurements of the actual instrument
- The EPT records every key, measures the pitch, B and partial strengths of each, then searches for the set of pitches that minimizes the entropy of the combined spectrum (coinciding partials give a sharp, low-entropy spectrum)
- The result is one target frequency per key
- The EPT's own tutorial (`tutorial/tutorial_en.html` in its repo) describes the three stages: recording, calculation, tuning

### The problem we had to fix: the number of keys

- Symptom
  - the piano being recorded stops at A7, but the EPT asked for recordings all the way to C8
  - going to the calculation stage failed with a complaint
- Cause
  - the EPT's piano data defaults to an 88-key keyboard (A0 to C8)
  - this piano has 85 keys (A0 to A7), so the app waited for three keys that do not exist
- Fix (a setting in the EPT, not a change to its code)
  - open the piano data dialog (the "edit piano sheet" dialog, which holds serial number, number of keys, key number of A, and keys on bass bridge)
  - set **Number of keys** to 85
  - check **Key number of A** (the position of A4 counted from the lowest key; the dialog counts from 1, so 49 for a keyboard starting at A0)
  - check **Keys on bass bridge** (default 28)
  - confirm and run the calculation again; it worked
- Caution
  - accepting the dialog applies a new keyboard configuration, and it may discard recordings already made, so save a copy first (this was not tested)
- The saved file confirms the setup
  - `numberOfKeys="85" keyNumberOfA="48" numberOfBassKeys="28"` (the file counts from 0, hence 48)

### The other problem we had: building the EPT on Windows with MinGW

The EPT had to be built from source (`C:\tuner\Entropy-Piano-Tuner`, Qt 6.12.0, MinGW 64-bit kit, built from Qt Creator). The first build failed at link time.

- Symptom
  - errors such as `undefined reference to 'fftw_solvtab_dft_standard'`, also `fftw_solvtab_rdft_r2r`, `_r2cb` and `_r2cf`
  - they were reported against `thirdparty/fftw3/fftw_subparts/libdft.a(conf.o)` and `librdft.a(conf.o)`
- What it was not
  - the symbols were present; for example `libdftscalarcodelets.a` defines `fftw_solvtab_dft_standard` (checked with `nm`)
  - the sources compiled fine; only the link of `fftw3.dll` failed
- Cause
  - FFTW is built by the EPT as many small static libraries (`libdft.a`, `librdft.a`, `libdftscalarcodelets.a` and so on) that are linked into one `fftw3.dll`
  - these libraries depend on each other in a circle (`libdft.a` needs the codelet table, the codelets need `libkernel.a`, and so on), so GNU ld must see them inside `-Wl,--start-group ... -Wl,--end-group`
  - `thirdparty/fftw3/fftw3/api/api.pro` did request a group, but as two separate `LIBS` items, and qmake moved the two flags next to each other
  - the generated `Makefile.Debug` had `-Wl,--start-group -Wl,--end-group -ldftscalar -ldftscalarcodelets ...`, an empty group with the libraries after it, so the circular references never resolved
  - how it was found: the `LIBS =` line in `build/.../thirdparty/fftw3/fftw3/api/Makefile.Debug`
- Fix, in `thirdparty/fftw3/fftw3/api/api.pro`
  - for `win32-g++`, build one single `-Wl,` option, comma separated, with full paths to the archives: `-Wl,--start-group,<path>/libdftscalar.a,...,<path>/libkernel.a,--end-group`
  - a single token without spaces cannot be split or reordered by qmake
  - quoting a space-separated string does not work, because g++ then receives it as one argument containing spaces
  - the trailing generic `else:LIBS += -ldftscalar ...` line is now restricted to platforms other than win32-g++, linux-g++ and android, so MinGW does not get the libraries twice
- After the change
  - in Qt Creator run Build, Run qmake, then rebuild (if the old Makefiles linger, delete the `fftw3/api` folder in the build directory)
  - the build then succeeded
- Not changed
  - `thirdparty/fftw3/fftw3_export.pri` has the same start-group pattern for a static FFTW build (`FFTW_LIBRARY_TYPE = static`)
  - the default on Windows is the DLL build, so it is not used here, but it would probably need the same treatment if static is ever chosen
- Running the result
  - the program is `build/Desktop_Qt_6_12_0_MinGW_64_bit_Debug/bin/entropypianotuner.exe`
  - run it from Qt Creator (Ctrl+R) so the DLL search path is set up; outside Qt Creator put `C:\Qt\6.12.0\mingw_64\bin`, the MinGW `bin` folder and the build's `thirdparty/fftw3` folder (holds `fftw3.dll`) on PATH
  - this was not tested from outside Qt Creator

### Recording and calculating (summary of the EPT workflow)

- Recording
  - choose recording mode and strike every key from left to right
  - for keys with several strings, record only one string and mute the others
  - wait for the green tick on each key; re-record or force key recognition (click the key twice, or press Enter) if needed
- Calculation
  - choose calculation mode, select the entropy minimizer and start the calculation
  - stop it once the green markers in the tuning curve window stop changing
  - then save the project
- Everything below assumes the file has been saved after the calculation

### The `.ept` file format

- It is plain XML, with CRLF line endings (about 11 MB for the 85-key piano here, mostly spectra)
- Structure of interest: `entropyPianoTunerFile > piano > keyboard > key`
  - `keyboard` attributes: `numberOfKeys`, `keyNumberOfA`, `numberOfBassKeys`
  - each `key` has attributes
    - `key`: index counted from 0 (0 is the lowest key)
    - `recordedFrequency`: the pitch as measured during recording
    - `measuredInharmonicity`: B
    - `computedFrequency`: the calculated target, which is what we extract
    - `tunedFrequency`: the pitch reached during tuning; it was 0 for every key until the tuning stage had been used
    - `recorded`: 1 if the key was recorded
    - `quality`: the signal quality shown after recording
  - each `key` also contains a `<spectrum>` of numbers and a number of `<peak>` elements

### Extracting the CSV

- Script: `ept_to_csv.py` (currently `/home/gabi/ept_to_csv.py`)
- Usage: `python3 ept_to_csv.py input.ept [output.csv]`
  - without an output name it writes `<input>_targets.csv`
  - it was run as `python3 -I ept_to_csv.py /mnt/c/tuner/mypiano.ept /mnt/c/tuner/mypiano_targets.csv`
- It reads each `key` element and writes `key` and `computedFrequency`, sorted by key

### The CSV format

- Two columns with a header: `key,frequency_hz`
- `key` is the 0-based index from the file
- `frequency_hz` is the calculated target
- Example (the first rows and some landmarks of the 85-key file)
  - key 0: 26.8409 Hz
  - key 1: 28.5027 Hz
  - key 48: 440.0 Hz
  - key 84: 3577.39 Hz
- The viewer assumes **key 0 is A0**, because the CSV has no note names. The note names are generated from the index (A4 is key 48). This is right for a keyboard that starts at A0, which is how the EPT file here is numbered. For a keyboard that starts elsewhere, the frequencies are still correct but the names would be wrong.

### Sanity checks that were run

- 85 rows, no zero frequencies
- Key 48 is exactly 440.0 Hz, which matches the concert pitch (440) and `keyNumberOfA="48"` in the file
- Octave deviation from a pure 2:1, computed from the CSV for the A-to-A octaves (`octave_cents.py`, currently `/home/gabi/octave_cents.py`, output `/mnt/c/tuner/mypiano_octaves.csv`); positive means wider than pure
  - A0 to A1: +28.0 cents
  - A1 to A2: +8.0 cents
  - A2 to A3: +5.0 cents
  - A3 to A4: +1.0 cents
  - A4 to A5: +4.0 cents
  - A5 to A6: +7.0 cents
  - A6 to A7: +17.0 cents
- Every octave is stretched, smallest near A3 to A4 and growing toward both ends, which is the expected shape for a piano
- The values come out suspiciously round (28.00, 7.99, 5.01, 1.00, 4.00, 7.00, 17.00); the reason was not investigated
- The lowest key is about 26.84 Hz, about 45 cents flat of a nominal A0 (27.5 Hz), plausible for a stretched bass but not verified against the piano

## Configuration constants

All at the top of `app.py` unless noted.

- `MAX_SECONDS = 16`: longest window, and the ring-buffer length
- `PEAK_HOLD_SECONDS = 10`: how long the y-axis ceiling remembers the highest level
- `DB_SPAN = 80`: dB shown below the held maximum (dB mode only)
- `LINEAR_Y = True`: plot linear amplitude instead of dB (set it to `False` for dB; this was added as a temporary switch)
- `TEXT_ENTRY`: the widget types that keep their own arrow keys
- The alpha of the cent lines is the last number in the `QColor(255, 0, 0, ...)` call in `Main.__init__` (0 to 255)
- `fs=48000` in `sources.py`: requested sample rate

## Known limitations

- The whole FFT is recomputed every 50 ms. At the longest window (16 s, about 768,000 samples) this may not keep up on a slow machine; it was not timed. A zoom-FFT (mixing the band down and decimating before the FFT) would give the same result for much less work.
- The "Peak" readout reports only the loudest peak, not one value per string.
- Note names assume key 0 is A0.
- The microphone is requested at 48 kHz; a device that does not support that may fail or be resampled.
- The default window (100,858 samples, about 2.1 s) is simply slider position 60 of 100 and is not a round number.
- Away from round center values the x-axis ticks are not round numbers, because one of them is always the exact center.
- At large spans the band is far from symmetric in cents.
- The EPT's target is calculated from measurements taken before you start tuning. Large pitch changes shift the tension of neighbouring strings, so tuning in passes may still be needed.
- The viewer shows where the partials are relative to a target; it does not model unisons or the inharmonicity of the piano itself.

## Development notes

- Developed from WSL (Ubuntu) against files on the Windows drive (`/mnt/c/tuner`), with the GUI run on native Windows in a miniforge environment
- Microphone input is much better on native Windows than through WSL's audio bridge, so run the live app on Windows
- The core can be tested anywhere with the synthetic source, for example by calling `band_spectrum` on `SyntheticSource(440.0).read_latest(...)` and checking the peaks (the three strings sit at about 439.24, 440.00 and 440.51 Hz and separate as the window grows)
- Windows executables may not be callable from every WSL shell; if `python.exe` returns exit code 127 from a sandboxed shell, run the commands from your own terminal instead
