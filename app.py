"""Zoomed live spectrum. Run: python app.py [--source mic|synth] [--center 440] [--span 20]"""
import argparse
import sys
import time
from collections import deque
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from core import band_spectrum, peak_freq, equal_temperament, load_targets_csv, center_ticks
from sources import MicSource, SyntheticSource

MAX_SECONDS = 16
PEAK_HOLD_SECONDS = 1
DB_SPAN = 80  # dB shown below the held maximum (dB mode only)
LINEAR_Y = True  # temporary: plot linear amplitude instead of dB
TEXT_ENTRY = (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox)  # keep their own arrow keys


class Main(QtWidgets.QWidget):
    def __init__(self, src, center, span, targets):
        super().__init__()
        self.src = src
        self.targets = targets
        self.setWindowTitle("Zoom spectrum")
        lay = QtWidgets.QVBoxLayout(self)

        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Frequency", "Hz")
        self.plot.setLabel("left", "Amplitude") if LINEAR_Y else self.plot.setLabel("left", "Level", "dB")
        self.curve = self.plot.plot(pen=pg.mkPen(width=1.5))
        self.plot.enableAutoRange(axis="y", enable=False)
        self.plot.enableAutoRange(axis="x", enable=False)  # x range is set explicitly per frame
        self.maxima = deque()  # (time, max dB of that frame)
        self.tick_key = None
        self.marker = pg.InfiniteLine(angle=90, pen=pg.mkPen("r", width=1, style=QtCore.Qt.DashLine))
        self.marker.setZValue(10)  # draw over the curve
        self.plot.addItem(self.marker)
        # dimmer lines every 5 cents, +/-25 cents around the marker
        self.cent_lines = []
        for c in (-25, -20, -15, -10, -5, 5, 10, 15, 20, 25):
            line = pg.InfiniteLine(angle=90, pen=pg.mkPen(QtGui.QColor(255, 0, 0, 200), width=1,
                                                          style=QtCore.Qt.DashLine))
            line.setZValue(9)
            self.plot.addItem(line)
            self.cent_lines.append((c, line))
        lay.addWidget(self.plot)

        row = QtWidgets.QHBoxLayout()
        self.win = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.win.setRange(0, 100)  # log scale 0.1 s .. 16 s
        self.win_lbl = QtWidgets.QLabel()
        self.n_edit = QtWidgets.QLineEdit()
        self.n_edit.setFixedWidth(90)
        self.n_edit.setValidator(QtGui.QIntValidator(256, int(self.src.fs * MAX_SECONDS)))
        self.n_samples = int(0.1 * (160 ** 0.6) * self.src.fs)
        self.sync_controls()
        self.win.valueChanged.connect(self.on_slider)
        self.n_edit.editingFinished.connect(self.on_edit)
        self.center = QtWidgets.QDoubleSpinBox()
        self.center.setRange(20, 8000); self.center.setDecimals(2); self.center.setValue(center)
        self.span = QtWidgets.QDoubleSpinBox()
        self.span.setRange(1, 1200); self.span.setDecimals(1); self.span.setValue(span)
        row.addWidget(QtWidgets.QLabel("Window")); row.addWidget(self.win, 1)
        row.addWidget(QtWidgets.QLabel("Samples")); row.addWidget(self.n_edit)
        row.addWidget(self.win_lbl)
        self.note = QtWidgets.QComboBox()
        self.note.setEditable(True)  # type to jump, e.g. "A4"
        self.note.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        for name, hz in targets:
            self.note.addItem(f"{name}  {hz:.2f} Hz", hz)
        nearest = min(range(len(targets)), key=lambda i: abs(targets[i][1] - center))
        self.note.setCurrentIndex(nearest)
        self.set_marker(targets[nearest][1])
        self.note.currentIndexChanged.connect(self.on_note)
        row.addWidget(QtWidgets.QLabel("Note")); row.addWidget(self.note)
        row.addWidget(QtWidgets.QLabel("Center Hz")); row.addWidget(self.center)
        row.addWidget(QtWidgets.QLabel("Span \u00b1 cents")); row.addWidget(self.span)
        lay.addLayout(row)
        self.info = QtWidgets.QLabel()
        lay.addWidget(self.info)

        self.win.setFocusPolicy(QtCore.Qt.NoFocus)  # slider never grabs the arrow keys
        QtWidgets.QApplication.instance().installEventFilter(self)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(50)
        # redraw at once on a band change instead of waiting for the next timer tick
        self.center.valueChanged.connect(self.update_plot)
        self.span.valueChanged.connect(self.update_plot)

    def sync_controls(self):
        """Push self.n_samples to the slider and text box without feedback loops."""
        T = self.n_samples / self.src.fs
        self.win.blockSignals(True)
        self.win.setValue(int(round(100 * np.log(T / 0.1) / np.log(160))))
        self.win.blockSignals(False)
        self.n_edit.setText(str(self.n_samples))

    def set_marker(self, hz):
        self.marker.setValue(hz)
        for c, line in self.cent_lines:
            line.setValue(hz * 2 ** (c / 1200))

    def on_note(self, i):
        if i < 0:
            return
        hz = self.note.itemData(i)
        self.center.setValue(hz)
        self.set_marker(hz)

    def step_note(self, d):
        i = min(max(self.note.currentIndex() + d, 0), self.note.count() - 1)
        self.note.setCurrentIndex(i)

    def step_window(self, seconds):
        n = self.n_samples + int(seconds * self.src.fs)
        self.n_samples = min(max(n, 256), int(self.src.fs * MAX_SECONDS))
        self.sync_controls()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QtCore.QEvent.MouseButtonPress and obj in (self.plot.viewport(), self):
            fw = QtWidgets.QApplication.focusWidget()  # click on the graph drops focus
            if fw is not None:
                fw.clearFocus()
            return False
        if t != QtCore.QEvent.KeyPress or QtWidgets.QApplication.activePopupWidget() is not None:
            return False
        fw = QtWidgets.QApplication.focusWidget()
        key = ev.key()
        if key == QtCore.Qt.Key_Escape and fw is not None:
            fw.clearFocus()
            return True
        if isinstance(fw, TEXT_ENTRY):
            return False
        actions = {QtCore.Qt.Key_Left: lambda: self.step_note(-1),
                   QtCore.Qt.Key_Right: lambda: self.step_note(1),
                   QtCore.Qt.Key_Up: lambda: self.step_window(1),
                   QtCore.Qt.Key_Down: lambda: self.step_window(-1)}
        if key in actions:
            actions[key]()
            return True
        return False

    def on_slider(self, v):
        self.n_samples = int(0.1 * (160 ** (v / 100)) * self.src.fs)
        self.n_edit.setText(str(self.n_samples))

    def on_edit(self):
        try:
            n = int(self.n_edit.text())
        except ValueError:
            n = self.n_samples
        self.n_samples = min(max(n, 256), int(self.src.fs * MAX_SECONDS))
        self.sync_controls()

    def update_plot(self):
        n = self.n_samples
        T = n / self.src.fs
        c, s = self.center.value(), self.span.value()  # span in cents, each side of center
        # symmetric in Hz so the center is exactly mid-axis; half-width is the mean of the
        # upper and lower cent offsets
        h = c * np.sinh(s * np.log(2) / 1200)
        lo, hi = c - h, c + h
        f, db = band_spectrum(self.src.read_latest(n), self.src.fs, lo, hi)
        if len(f) < 3:
            return
        y = 10 ** (db / 20) if LINEAR_Y else db
        self.curve.setData(f, y)
        self.plot.setXRange(lo, hi, padding=0)
        if (c, h) != self.tick_key:  # only rebuild the tick labels when the band changed
            self.tick_key = (c, h)
            self.plot.getAxis("bottom").setTicks([center_ticks(c, h)])
        now = time.monotonic()
        self.maxima.append((now, float(y.max())))
        while self.maxima[0][0] < now - PEAK_HOLD_SECONDS:
            self.maxima.popleft()
        top = max(m for _, m in self.maxima)
        self.plot.setYRange(0 if LINEAR_Y else top - DB_SPAN, top, padding=0.02)
        self.win_lbl.setText(f"{T:.2f} s  (~{1 / T:.2f} Hz resolution)")
        self.info.setText(f"Peak: {peak_freq(f, db):.3f} Hz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["mic", "synth"], default="synth")
    ap.add_argument("--center", type=float, default=440.0)
    ap.add_argument("--span", type=float, default=50.0, help="cents on each side of the center")
    ap.add_argument("--device", default=None)
    ap.add_argument("--targets", help="CSV with key,frequency_hz (key 0 = A0); default: equal temperament")
    a = ap.parse_args()
    src = MicSource(device=a.device) if a.source == "mic" else SyntheticSource(a.center)
    app = QtWidgets.QApplication(sys.argv)
    targets = load_targets_csv(a.targets) if a.targets else equal_temperament()
    w = Main(src, a.center, a.span, targets)
    w.resize(1000, 600)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
