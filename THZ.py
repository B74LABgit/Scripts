from __future__ import annotations
import sys
import os, os.path
from datetime import datetime
import numpy as np
import pyvisa
#import sched
import time
import math
import cv2
import json
import threading
from multiprocessing import Process
from scipy.signal import lombscargle
from scipy.fft import fft, fftfreq
from astropy.stats import LombScargle
from lakeshore import Model336

from matplotlib.backends.qt_compat import QtCore, QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvas
import matplotlib as mpl
#import matplotlib.figure as mpl_fig
#import matplotlib.animation as anim
mpl.rcParams.update(
    {
        'text.usetex': False,
        'font.family': 'stixgeneral',
        'mathtext.fontset': 'stix',
    }
)
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QDir
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QComboBox, QSpinBox, QFrame, QLineEdit, QTextEdit, QFileDialog, QDialog, QCheckBox, QGroupBox,
                             QToolTip, QProgressBar, QMessageBox, QLabel, QTabWidget, QVBoxLayout, QHBoxLayout, QWidget, QDoubleSpinBox, QDesktopWidget)
from qtwidgets import AnimatedToggle

### DISCORD
from discord import SyncWebhook
def send_discord(message, ntries=5):
    try: 
        webhook = SyncWebhook.from_url("https://discord.com/api/webhooks/1014249757968957441/Y_E7z5mCl3s9hmXI41FyEo1fQaBtROYS9qcbQGlaa6AIApsMvTRCSxbAtd_J9_hr57NB")
        webhook.send(message)
    except Exception as e: 
        if ntries==0: print("\nFailed to send message: ", e); return
        time.sleep(1); send_discord(message, ntries=ntries-1)    
### 

### SMS
import smtplib
def send_sms(message, ntries=5):
    try: 
        smtpserver = smtplib.SMTP("smtp.gmail.com", 587)
        smtpserver.ehlo()
        smtpserver.starttls()
        sender = 'b74lab@gmail.com'
        passwd = 'kmphigyzzdocbzay'
        smtpserver.login(sender, passwd)
        smtpserver.sendmail(sender, '6174595329@txt.att.net', str(message)); print("\nSuccess sending message.")
    except Exception as e: 
        if ntries==0: print("\nFailed to send message: ", e); return
        time.sleep(1); send_sms(message, ntries=ntries-1)
###

dictionary = {
  '1': {"label": 'Sample axis', "lower_bound": 0, "upper_bound": 1000, "home": 0, "p0": 0, "off": 0 },
  '2': {"label": 'THz axis', "lower_bound": 0, "upper_bound": 1000, "home": 0, "p0": 0, "off": 0 },
  '3': {"label": 'Gate axis', "lower_bound": 0, "upper_bound": 1000, "home": 0, "p0": 0, "off": 0 },
}

def update_dictionary():
    with open('config.json', 'w') as fp:
        json.dump(dictionary, fp)
if not os.path.exists('config.json'): update_dictionary()
else:
    with open('config.json', 'r') as fp: dictionary = json.load(fp)


AXISlabels = [dictionary[i]['label'] for i in ['1','2','3']] # ['Sample axis', 'THz axis', 'Gate axis']

TIMEvalues = [10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3, 30e-3, 100e-3, 300e-3, 1, 3, 10, 30, 100, 300, 1000, 3000, 10000, 30000]
TIMEconstants = [0, 0]

Y2values = []; Y2last = 0
Yvalues = [];  Ylast = 0
Xvalues = []; Xlast = [0,0,0]
AXISunits = ['mm', 'mm', 'mm']
continue_background = True
continue_plot = True
### INSTRUMENTS
rm = pyvisa.ResourceManager()
instruments_list = rm.list_resources()
instrLOCKIN = [] ; instrSTAGE = [] # erase
for instrument in instruments_list:
    try:
        instr = rm.open_resource(instrument); instr.clear()
        identity = instr.query('*IDN?')
        if 'ESP301' in identity: instrSTAGE.append(instr)
        if 'SR830'  in identity: instrLOCKIN.append(instr)
    except: continue
NinstrLOCKIN = len(instrLOCKIN); NinstrSTAGE = len(instrSTAGE)
if NinstrLOCKIN == 0: sys.exit("LOCK-IN was not detected.")
if NinstrSTAGE == 0: sys.exit("STAGE CONTROLLER was not detected.")

try:
    instr_rotation = rm.open_resource('ASRL4::INSTR')
    instr_rotation.baud_rate = 921600
except: pass

try:
    instr_OSCILLOSCOPE = rm.open_resource('USB0::0x0699::0x03A6::C051988::INSTR');
except: pass
###

### STYLE
my_style = "<p style=\"  font-family:\'Times New Roman\'; font-size:25px;   \">"
my_style2 = "<p style=\"  font-family:\'Times New Roman\'; font-size:45px;   \">"


# 2fc8ea

GLOBAL_STYLE = """
QLineEdit { 
     font-size: 30px; font-family: "Times New Roman";  
    }
QCheckBox::indicator {
                               width :30px;
                               height :30px;
                               }
QLabel { 
     font-size: 20px; font-family: "Times New Roman";  
    }
QComboBox { 
    background:#fffc38; font-size: 30px; font-family: "Times New Roman";  
    }
QDoubleSpinBox { 
    font-size: 30px; font-family: "Times New Roman"; 
    }
QSpinBox {  
    background:#09d710; font-size: 30px; font-family: "Times New Roman"; 
    }
QPushButton { 
    background:#f0c541; font-size: 25px; font-family:"Times New Roman"; 
    }
QTabWidget { 
    background:#e6fdc5; font-size: 15px; font-family:"Times New Roman";  
    }
QMessageBox {
    background:#73d1fa; font-size: 20px; font-family:"Times New Roman";  
    }
QGroupBox {
    font-size: 20px; font-weight: bold; font-family:"Times New Roman";  border: 1.5px solid black;
    }
"""
###

### COMMUNICATION
def instr_action(instr, Query, rep=True, ntries=5):
    try:
        #instr.clear()
        instr.write(Query) # +';*OPC?'
    except:
        time.sleep(0.4); instr.clear(); time.sleep(0.4); instr.close();  time.sleep(0.4); instr.open(); time.sleep(0.4);
        if ntries==0: print("ERROR: ", Query); raise ValueError('INSTRUMENT error.'); return;
        if rep: time.sleep(0.5); instr_action(instr, Query, ntries=ntries-1)
def instr_query(instr, Query, rep=True, type=str, ntries=5):
    try:
        #instr.clear()
        to_return = instr.query(Query)
        return type(to_return)
    except:
        time.sleep(0.4); instr.clear(); time.sleep(0.4); instr.close();  time.sleep(0.4); instr.open(); time.sleep(0.4);
        if ntries==0: print("ERROR: ", Query); raise ValueError('INSTRUMENT error.'); return; 
        if rep: time.sleep(0.5); instr_query(instr, Query, type=type, ntries=ntries-1)
###

def getOUTP(instr, ind, rep=True):
    return instr_query(instr, 'OUTP? '+str(ind), rep, type=float)
        
### UNITS
class Units:
    def __init__(self):
        global si;
        si = {
              -18 : {'multiplier' : 10 ** 18, 'prefix' : 'a'},
              -17 : {'multiplier' : 10 ** 18, 'prefix' : 'a'},
              -16 : {'multiplier' : 10 ** 18, 'prefix' : 'a'},
              -15 : {'multiplier' : 10 ** 15, 'prefix' : 'f'},
              -14 : {'multiplier' : 10 ** 15, 'prefix' : 'f'},
              -13 : {'multiplier' : 10 ** 15, 'prefix' : 'f'},
              -12 : {'multiplier' : 10 ** 12, 'prefix' : 'p'},
              -11 : {'multiplier' : 10 ** 12, 'prefix' : 'p'},
              -10 : {'multiplier' : 10 ** 12, 'prefix' : 'p'},
              -9 : {'multiplier' : 10 ** 9, 'prefix' : 'n'},
              -8 : {'multiplier' : 10 ** 9, 'prefix' : 'n'},
              -7 : {'multiplier' : 10 ** 9, 'prefix' : 'n'},
              -6 : {'multiplier' : 10 ** 6, 'prefix' : '\u03BC'},
              -5 : {'multiplier' : 10 ** 6, 'prefix' : '\u03BC'},
              -4 : {'multiplier' : 10 ** 6, 'prefix' : '\u03BC'},
              -3 : {'multiplier' : 10 ** 3, 'prefix' : 'm'},
              -2 : {'multiplier' : 10 ** 2, 'prefix' : 'c'},
              -1 : {'multiplier' : 10 ** 1, 'prefix' : 'd'},
               0 : {'multiplier' : 1, 'prefix' : ''},
               1 : {'multiplier' : 10 ** 1, 'prefix' : 'da'},
               2 : {'multiplier' : 10 ** 3, 'prefix' : 'k'},
               3 : {'multiplier' : 10 ** 3, 'prefix' : 'k'},
               4 : {'multiplier' : 10 ** 3, 'prefix' : 'k'},
               5 : {'multiplier' : 10 ** 3, 'prefix' : 'k'},
               6 : {'multiplier' : 10 ** 6, 'prefix' : 'M'},
               7 : {'multiplier' : 10 ** 6, 'prefix' : 'M'},
               8 : {'multiplier' : 10 ** 6, 'prefix' : 'M'},
               9 : {'multiplier' : 10 ** 9, 'prefix' : 'G'},
              10 : {'multiplier' : 10 ** 9, 'prefix' : 'G'},
              11 : {'multiplier' : 10 ** 9, 'prefix' : 'G'},
              12 : {'multiplier' : 10 ** 12, 'prefix' : 'T'},
              13 : {'multiplier' : 10 ** 12, 'prefix' : 'T'},
              14 : {'multiplier' : 10 ** 12, 'prefix' : 'T'},
              15 : {'multiplier' : 10 ** 15, 'prefix' : 'P'},
              16 : {'multiplier' : 10 ** 15, 'prefix' : 'P'},
              17 : {'multiplier' : 10 ** 15, 'prefix' : 'P'},
              18 : {'multiplier' : 10 ** 18, 'prefix' : 'E'},
              }
        
    def convert(self, number):
        if number < 0:
            negative = True;
        else:
            negative = False;
        if negative:
            number = number - (number*2);
        exponent = int(math.log10(number));
        if negative:
            number = number - (number*2);

        if exponent < 0:
            exponent = exponent-1;
            return [number * si[exponent]['multiplier'], si[exponent]['prefix']]; 
        elif exponent > 0:
            return [number / si[exponent]['multiplier'], si[exponent]['prefix']]; 
        elif exponent == 0:
            return [number, ''];

units = Units();
###

### Widgets
def QLabel_(Text = '', Alignment = Qt.AlignCenter):
    WIDGET = QLabel();
    WIDGET.setText(Text); 
    WIDGET.setAlignment(Alignment);
    return WIDGET
def QSpinBox_(Minimum = 0, Maximum = 1000 , Value = None, Changed = None, Suffix = ''):
    WIDGET = QSpinBox()
    WIDGET.setMinimum(Minimum)
    WIDGET.setMaximum(Maximum)
    WIDGET.setValue(Value)
    if Changed: WIDGET.valueChanged.connect(Changed)
    WIDGET.setSuffix(Suffix)
    return WIDGET
def QDoubleSpinBox_(Minimum = 0, Maximum = 1000, Value = None, Changed = None, Suffix = '', SingleStep = 1, KeyboardTracking = False, FixedWidth = None):
    WIDGET = QDoubleSpinBox()
    WIDGET.setMinimum(Minimum)
    WIDGET.setMaximum(Maximum)
    WIDGET.setDecimals(4)
    WIDGET.setValue(Value)
    if Changed: WIDGET.valueChanged.connect(Changed)
    if FixedWidth: WIDGET.setFixedWidth(FixedWidth)
    WIDGET.setSingleStep(SingleStep)
    WIDGET.setSuffix(Suffix)
    WIDGET.setKeyboardTracking(KeyboardTracking)
    return WIDGET
def QComboBox_(Items = None, CurrentIndex = 0, CurrentIndexChanged = None, View = False, Editable = True):
    WIDGET = QComboBox()
    WIDGET.setEditable(Editable)
    WIDGET.addItems(Items)
    WIDGET.setCurrentIndex(CurrentIndex)
    WIDGET.currentIndexChanged.connect(CurrentIndexChanged)
    view = WIDGET.view(); view.setHidden(View);
    return WIDGET
def QPushButton_(Name = '', Clicked = None): 
    WIDGET =  QPushButton(Name)
    WIDGET.setToolTip(Name)
    WIDGET.clicked.connect(Clicked)
    return WIDGET

def QLQComboBox_(Text, Items = None, CurrentIndex = 0, CurrentIndexChanged = None, View = False, Editable = True):
    Dlayout = QtWidgets.QHBoxLayout()
    Dlayout.addWidget( QLabel_(Text)  )
    Dlayout.addWidget( QComboBox_(Items, CurrentIndex, CurrentIndexChanged, View, Editable) )
    return Dlayout
def QLSpinBox_(Text, Minimum = 0, Maximum = 1000 , Value = None, Changed = None, Suffix = ''):
    Dlayout = QtWidgets.QHBoxLayout()
    Dlayout.addWidget( QLabel_(Text)  )
    Dlayout.addWidget( QSpinBox_(Minimum , Maximum  , Value , Changed , Suffix )  )
    return Dlayout
def QLDoubleSpinBox_(Text, Minimum = 0, Maximum = 1000, Value = None, Changed = None, Suffix = '', SingleStep = 1, KeyboardTracking = False, FixedWidth = None):
    Dlayout = QtWidgets.QHBoxLayout()
    Dlayout.addWidget( QLabel_(Text)  )
    Dlayout.addWidget( QDoubleSpinBox_(Minimum , Maximum , Value , Changed , Suffix , SingleStep , KeyboardTracking , FixedWidth)  )
    return Dlayout
def addWidLay(parent, TOADD):
    try: parent.addWidget(TOADD)
    except: parent.addLayout(TOADD)
    
class Window2(QMainWindow):                         
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Window22222")
        
class LOCKIN(QMainWindow):
    def __init__(self, instr_index):
        super().__init__()
        global TIMEconstants
        self.setWindowTitle("Lock-In Amplifier")
        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        self.layout = QtWidgets.QGridLayout(self._main)
        self.setStyleSheet(  GLOBAL_STYLE  )

        self.instr = instrLOCKIN[instr_index]
        self.instr_index = instr_index
        ## Options
        self.tabs = QTabWidget()
        self.tab1 = QWidget(); self.tab2 = QWidget(); self.tab3 = QWidget();
        self.tabs.addTab(self.tab1, "REFERENCE and PHASE"); self.tabs.addTab(self.tab2, "INPUT and FILTER"); self.tabs.addTab(self.tab3, "GAIN and TIME CONSTANT");
        self.tab1.layout = QVBoxLayout(self); self.tab2.layout = QVBoxLayout(self); self.tab3.layout = QVBoxLayout(self);
        
        # Tab1
        Dlayout = QtWidgets.QVBoxLayout()
        
        Dlabel =  QLabel_(my_style+"<b>Phase Shift</b>");
        self.PHAS_ = QDoubleSpinBox_(-1000.00, 1000.00, self.get_phase_shift(), self.phase_shift, "\u00B0")
        for WIDGET in [Dlabel, self.PHAS_]: Dlayout.addWidget(WIDGET); 

        Dlabel =  QLabel_(my_style+"<b>Reference Source</b>");
        self.FMOD_ = QComboBox_(["External", "Internal"], self.get_reference_source(), self.reference_source);
        for WIDGET in [Dlabel, self.FMOD_]: Dlayout.addWidget(WIDGET); 

        Dlabel =  QLabel_(my_style+"<b>Reference Frequency</b>")
        self.FREQ_ = QDoubleSpinBox_(0.00, 102000.00, self.get_reference_frequency(), self.reference_frequency, " Hz")
        for WIDGET in [Dlabel,  self.FREQ_]: Dlayout.addWidget(WIDGET);
        
        Dlabel =  QLabel_(my_style+"<b>External Reference Slope</b>")
        self.RSLP_ = QComboBox_(["Sine", "TTL Rising", "TTL Falling"], self.get_external_reference_slope(), self.external_reference_slope);
        for WIDGET in [Dlabel,  self.RSLP_]: Dlayout.addWidget(WIDGET);

        Dlabel =  QLabel_(my_style+"<b>Detection Harmonic</b>")
        self.HARM_ = QSpinBox_(1, 19999, self.get_detection_harmonic(), self.detection_harmonic)
        for WIDGET in [Dlabel,  self.HARM_]: Dlayout.addWidget(WIDGET);
        
        Dlabel =  QLabel_(my_style+"<b>Sine Output Amplitude</b>") 
        self.SLVL_ = QDoubleSpinBox_(0.004, 5.000, self.get_sine_output_amplitude(), self.sine_output_amplitude, " Vrms")
        for WIDGET in [Dlabel,  self.SLVL_]: Dlayout.addWidget(WIDGET);
        
        self.tab1.layout.addLayout(Dlayout); self.tab1.setLayout(self.tab1.layout)
        
        # Tab2
        Dlayout = QtWidgets.QVBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Input Configuration</b>")
        self.ISRC_ = QComboBox_(["A", "A-B", " I (1 M\u03A9)", "I (100 M\u03A9)"], self.get_input_configuration(), self.input_configuration)
        for WIDGET in [Dlabel,  self.ISRC_]: Dlayout.addWidget(WIDGET);

        Dlabel =  QLabel_(my_style+"<b>Input Shield Grounding</b>")
        self.IGND_ = QComboBox_(["Float", "Ground"], self.get_shield_grounding(), self.shield_grounding); 
        for WIDGET in [Dlabel,  self.IGND_]: Dlayout.addWidget(WIDGET);
        
        Dlabel =  QLabel_(my_style+"<b>Input Coupling</b>")
        self.ICPL_ = QComboBox_(["AC", "DC"], self.get_coupling(), self.coupling); 
        for WIDGET in [Dlabel,  self.ICPL_]: Dlayout.addWidget(WIDGET);

        Dlabel =  QLabel_(my_style+"<b>Line Notch Filters</b>")
        self.ILIN_ = QComboBox_(["Out", "Line In", "2xLine In", "Both In"], self.get_line_notch_filters(), self.line_notch_filters); 
        for WIDGET in [Dlabel,  self.ILIN_]: Dlayout.addWidget(WIDGET);
        
        self.tab2.layout.addLayout(Dlayout); self.tab2.setLayout(self.tab2.layout)
        
        # Tab 3
        Dlayout = QtWidgets.QVBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Sensitivity</b>")
        self.SENS_ = QComboBox_(["2 nV", "5 nV", "10 nV", "20 nV", "50 nV", "100 nV", "200 nV", "500 nV", "1 µV", "2 µV", "5 µV", "10 µV", "20 µV", "50 µV", "100 µV", "200 µV", "500 µV", "1 mV", "2 mV", "5 mV", "10 mV", "20 mV", "50 mV", "100 mV", "200 mV", "500 mV", "1 V"], self.get_sensitivity(), self.sensitivity);
        for WIDGET in [Dlabel,  self.SENS_]: Dlayout.addWidget(WIDGET);

        Dlabel =  QLabel(my_style+"<b>Dynamic Reserve Mode</b>") 
        self.RMOD_ = QComboBox_(["High Reserve", "Normal", "Low Noise"], self.get_reserve_mode(), self.reserve_mode);
        for WIDGET in [Dlabel,  self.RMOD_]: Dlayout.addWidget(WIDGET);

        dvar = self.get_time_constant()
        TIMEconstants[instr_index] =  TIMEvalues[dvar]
        Dlabel =  QLabel_(my_style+"<b>Time Constant </b>")
        self.OFLT_ = QComboBox_(["10 µs", "30 µs", "100 µs", "300 µs", "1 ms", "3 ms", "10 ms", "30 ms", "100 ms", "300 ms", "1 s", "3 s", "10 s", "30 s", "100 s", "300 s", "1 ks", "3 ks", "10 ks", "30 ks"], dvar, self.time_constant); 
        for WIDGET in [Dlabel,  self.OFLT_]: Dlayout.addWidget(WIDGET);

        Dlabel =  QLabel_(my_style+"<b>Low Pass Filter Slope</b>")
        self.OFSL_ = QComboBox_(["6 dB/oct", "12 dB/oct", "18 dB/oct", "24 dB/oct"], self.get_low_pass_filter(), self.low_pass_filter);
        for WIDGET in [Dlabel,  self.OFSL_]: Dlayout.addWidget(WIDGET);

        Dlabel =  QLabel_(my_style+"<b>Synchronous Filter</b>")
        self.SYNC_ = QComboBox_(["Off", "On below 200 Hz (1)"], self.get_synchronous_filter(), self.synchronous_filter);
        for WIDGET in [Dlabel,  self.SYNC_]: Dlayout.addWidget(WIDGET);
        
        self.tab3.layout.addLayout(Dlayout); self.tab3.setLayout(self.tab3.layout)

    
        self.layout.addWidget(self.tabs, 0, 0, 3, 1)

        # LOCK-IN
        Dlayout = QtWidgets.QVBoxLayout()
        Dlabel =  QLabel_(my_style2+"<b>LOCK-IN " + str(instr_index+1) +"</b>")
        Dlayout.addWidget(Dlabel);
        #self.sLOCKIN = QSpinBox_(1, NinstrLOCKIN, 1, self.select_lockin)
        #for WIDGET in [Dlabel,  self.sLOCKIN]: Dlayout.addWidget(WIDGET);
        #self.layout.addLayout(Dlayout, 0, 1, 1, 1)
        if NinstrLOCKIN > 1:
            if instr_index == 0:
                self.axisP1s = QPushButton_("\u2B9E", self.axisP1); self.axisP1s.setStyleSheet("QPushButton { background:#CFFF00; }")
                Dlayout.addWidget(self.axisP1s);
            elif instr_index == 1:
                self.axisM1s = QPushButton_("\u2B9C", self.axisM1); self.axisM1s.setStyleSheet("QPushButton { background:#CFFF00; }")
                Dlayout.addWidget(self.axisM1s);
        self.layout.addLayout(Dlayout, 0, 1, 1, 1)

        # Offset
        layout3 = QtWidgets.QVBoxLayout()
        X1i, X2i = self.getXoffset_expand(); Y1i, Y2i = self.getYoffset_expand(); R1i, R2i = self.getRoffset_expand()
        Dlayout = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Offset and Expand</b>");
        layout3.addWidget(Dlabel)
        
        self.tabs = QTabWidget()
        self.tab1 = QWidget(); self.tab2 = QWidget(); self.tab3 = QWidget(); self.tab4 = QWidget(); self.tab5 = QWidget()
        self.tabs.addTab(self.tab1, "X"); self.tabs.addTab(self.tab2, "Y"); self.tabs.addTab(self.tab3, "R"); 
        self.tab1.layout = QVBoxLayout(self); self.tab2.layout = QVBoxLayout(self); self.tab3.layout = QVBoxLayout(self); 
        
        # Tab1
        Dlayout1 = QtWidgets.QVBoxLayout(); Dlayout = QtWidgets.QHBoxLayout()
        
        Dlabel =  QLabel_(my_style+"<b>Offset</b>")
        self.Xoffset_ = QDoubleSpinBox_(-105.00, 105.00, X1i, self.Xoffset)
        self.Xautooffset_ = QPushButton_('Auto Offset', self.Xautooffset)
        for WIDGET in [Dlabel,  self.Xoffset_, self.Xautooffset_]: Dlayout.addWidget(WIDGET);
        Dlayout1.addLayout(Dlayout)
        Dlabel =  QLabel("", self); Dlabel.setText(my_style+"<b>Expand</b>"); Dlabel.setAlignment(Qt.AlignCenter);
        self.Xexpand_ = QComboBox_(["\u00D71", "\u00D710", "\u00D7100"], X2i, self.Xexpand)
        for WIDGET in [Dlabel,  self.Xexpand_]: Dlayout1.addWidget(WIDGET);
        
        self.tab1.layout.addLayout(Dlayout1); self.tab1.setLayout(self.tab1.layout)
        
        # Tab2
        Dlayout1 = QtWidgets.QVBoxLayout(); Dlayout = QtWidgets.QHBoxLayout()
        
        Dlabel =  QLabel_(my_style+"<b>Offset</b>");
        self.Yoffset_ = QDoubleSpinBox_(-105.00, 105.00, Y1i, self.Yoffset)
        self.Yautooffset_ = QPushButton_('Auto Offset', self.Yautooffset)
        for WIDGET in [Dlabel,  self.Yoffset_, self.Yautooffset_]: Dlayout.addWidget(WIDGET);
        Dlayout1.addLayout(Dlayout)
        Dlabel =  QLabel("", self); Dlabel.setText(my_style+" <b>Expand</b>"); Dlabel.setAlignment(Qt.AlignCenter);
        self.Yexpand_ = QComboBox_(["\u00D71", "\u00D710", "\u00D7100"], Y2i, self.Yexpand)
        for WIDGET in [Dlabel,  self.Yexpand_]: Dlayout1.addWidget(WIDGET);

        self.tab2.layout.addLayout(Dlayout1); self.tab2.setLayout(self.tab2.layout)
        
        # Tab3
        Dlayout1 = QtWidgets.QVBoxLayout(); Dlayout = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+" <b>Offset</b>");
        self.Roffset_ = QDoubleSpinBox_(-105.00, 105.00, R1i, self.Roffset)
        self.Rautooffset_ = QPushButton_('Auto Offset', self.Rautooffset)
        for WIDGET in [Dlabel,  self.Roffset_, self.Rautooffset_]: Dlayout.addWidget(WIDGET);
        Dlayout1.addLayout(Dlayout)
        Dlabel =  QLabel_(my_style+" <b>Expand</b>");
        self.Rexpand_ = QComboBox_(["\u00D71", "\u00D710", "\u00D7100"], R2i, self.Rexpand)
        for WIDGET in [Dlabel,  self.Rexpand_]: Dlayout1.addWidget(WIDGET);

        self.tab3.layout.addLayout(Dlayout1); self.tab3.setLayout(self.tab3.layout)
        
        layout3.addWidget(self.tabs)
        self.layout.addLayout(layout3, 2, 1, 1, 1)
        
        self.layout.setColumnStretch(0, 2); self.layout.setColumnStretch(1, 2);  self.layout.setColumnStretch(2, 2);
        self.layout.setRowStretch(1, 5)
        
       
        self.setLayout(self.layout)
        #self.showMaximized()
        #self.show()
        return     
    
    def axisM1(self):
        self.hide(); myLOCKINs[self.instr_index-1].show()
    def axisP1(self):
        self.hide(); myLOCKINs[self.instr_index+1].show()
    
    def select_lockin(self, value):
        self.hide()
        self.__init__(value)
        self.show()    
    # DATA TRANSFER 
    def getOUTP(self, ind):
        return instr_query(self.instr, 'OUTP? '+str(ind), type=float)
    def getOUTR(self, ind):
        return instr_query(self.instr, 'OUTR? '+str(ind), type=float)
    def get_reference_frequency(self):
        return instr_query(self.instr, 'FREQ?', type=float)
        
    # REFERENCE and PHASE 
    def phase_shift(self, value): # x degrees
        Query = 'PHAS '+str(value)
        instr_action(self.instr, Query)
    def get_phase_shift(self):
        return instr_query(self.instr, 'PHAS?', type=float)
    def reference_source(self, value): # External (0) or Internal (1)
        Query = 'FMOD '+str(value)
        instr_action(self.instr, Query)
    def get_reference_source(self): # External (0) or Internal (1)
        QAr = instr_query(self.instr, 'FMOD?')
        return int(QAr)
    def reference_frequency(self, value): # f Hz
        hrm = self.get_detection_harmonic()
        if value*hrm <= 102000:
            Query = 'FREQ '+str(value)
            instr_action(self.instr, Query)
            #self.set_time_constant_list()
    def external_reference_slope(self, value): # Sine(0), TTL Rising (1), or TTL Falling (2)
        Query = 'RSLP '+str(value)
        instr_action(self.instr, Query)
    def get_external_reference_slope(self):
        return instr_query(self.instr, 'RSLP?', type=int)
    def detection_harmonic(self, value): #  1 = i = 19999 and i•f = 102 kHz
        freq = self.get_reference_frequency()
        if freq*value <= 102000:
            Query = 'HARM '+str(value)
            instr_action(self.instr, Query)
    def get_detection_harmonic(self): # 1
        return instr_query(self.instr, 'HARM?', type=int)
    def sine_output_amplitude(self, value): #  0.004 = x =5.000
        Query = 'SLVL '+str(value) 
        instr_action(self.instr, Query)
    def get_sine_output_amplitude(self):
        return instr_query(self.instr, 'SLVL?', type=float)
    
    # GAIN and TIME CONSTANT
    def sensitivity(self, value): # 2 nV (0) through 1 V (26)
        Query = 'SENS '+str(value)
        instr_action(self.instr, Query)
        #self.set_time_constant_list()
    def get_sensitivity(self): # 17
        return instr_query(self.instr, 'SENS?', type=int)
    def reserve_mode(self, value): # HighReserve (0), Normal (1), or Low Noise (2)
        Query = 'RMOD '+str(value)
        instr_action(self.instr, Query)
        #self.set_time_constant_list()
    def get_reserve_mode(self):
        return instr_query(self.instr, 'RMOD?', type=int)
    def time_constant(self, value): # 10 µs (0) through 30 ks (19)
        Query = 'OFLT '+str(value)
        instr_action(self.instr, Query)
    def get_time_constant(self):
        return instr_query(self.instr, 'OFLT?', type=int)
    def low_pass_filter(self, value): # 6 (0), 12 (1), 18 (2) or 24 (3) dB/oct
        Query = 'OFSL '+str(value)
        instr_action(self.instr, Query)
        #self.set_time_constant_list()
    def get_low_pass_filter(self):
        return instr_query(self.instr, 'OFSL?', type=int)   
    def synchronous_filter(self, value): #  Off (0) or On below 200 Hz (1)
        Query = 'SYNC '+str(value)
        instr_action(self.instr, Query)
    def get_synchronous_filter(self):
        return instr_query(self.instr, 'SYNC?', type=int)

    def get_reserve_dB(self):
        global dB_matrix
        ind1 = self.get_sensitivity()
        Ind2 = self.get_reserve_mode()
        ind2 = 0 if Ind2==2 else 1 if Ind2==1 else 2            
        actual_dynamic_reserve = dB_matrix[ind1, ind2]
        
        X1i, X2i = instr_query(self.instr, 'OEXP? 1').split('\n')[0].split(',')
        Y1i, Y2i = instr_query(self.instr, 'OEXP? 2').split('\n')[0].split(',')
        R1i, R2i = instr_query(self.instr, 'OEXP? 3').split('\n')[0].split(',')
        XYRexpand = [int(X2i), int(Y2i), int(R2i)]
        maxXYRexpand = max(XYRexpand)
        if maxXYRexpand==0:
            actual_dynamic_reserve += 0
        elif maxXYRexpand==1:
            actual_dynamic_reserve += 20
        else:
            actual_dynamic_reserve += 40
        return actual_dynamic_reserve

  
    # INPUT and FILTER
    def input_configuration(self, value): # A (0), A-B (1) , I (1 M?) (2) or I (100 M?) (3)
        Query = 'ISRC '+str(value)
        instr_action(self.instr, Query)
    def get_input_configuration(self):
        return instr_query(self.instr, 'ISRC?', type=int)
    def shield_grounding(self, value): # Float (0) or Ground (1)
        Query = 'IGND '+str(value)
        instr_action(self.instr, Query)
    def get_shield_grounding(self):
        return instr_query(self.instr, 'IGND?', type=int)
    def coupling(self, value): # AC (0) or DC (1)
        Query = 'ICPL '+str(value)
        instr_action(self.instr, Query)
    def get_coupling(self):
        return instr_query(self.instr, 'ICPL?', type=int)
    def line_notch_filters(self, value): # Out (0), Line In (1) , 2xLine In (2), or Both In (3)
        Query = 'ILIN '+str(value)
        instr_action(self.instr, Query)
    def get_line_notch_filters(self):
        return instr_query(self.instr, 'ILIN?', type=int)
    
    # DISPLAY and OUTPUT
    def DOdisplay1(self, value):
        global display1xr
        Ji, Ki = instr_query(self.instr, 'DDEF? 1').split('\n')[0].split(',')
        display1xr = value
        Query = 'DDEF 1,'+str(value)+', '+Ki
        instr_action(self.instr, Query)
    def DOratio1(self, value):
        Ji, Ki = instr_query(self.instr, 'DDEF? 1').split('\n')[0].split(',')
        Query = 'DDEF 1, '+Ji+', '+str(value)
        instr_action(self.instr, Query) 
    def getDOdisplay_ratio1(self):
        Ji, Ki = instr_query(self.instr, 'DDEF? 1').split('\n')[0].split(',')
        return int(Ji), int(Ki)
    def output_source1(self, value):
        Query = 'FPOP 1, '+str(value)
        instr_action(self.instr, Query) 
    def get_output_source1(self): 
        Li = instr_query(self.instr, 'FPOP? 1').split('\n')[0]
        return int(Li)  
    
    def DOdisplay2(self, value):
        global display2yt
        J, K = instr_query(self.instr, 'DDEF? 1').split('\n')[0].split(',')
        display2yt = value
        Query = 'DDEF 2,'+str(value)+', '+K
        instr_action(self.instr, Query)  
    def DOratio2(self, value):
        J, K = instr_query(self.instr, 'DDEF? 2').split('\n')[0].split(',')
        Query = 'DDEF 2, '+J+', '+str(value)
        instr_action(self.instr, Query) 
    def getDOdisplay_ratio2(self):
        J, K = instr_query(self.instr, 'DDEF? 2').split('\n')[0].split(',')
        return int(J), int(K)
    def output_source2(self, value):
        Query = 'FPOP 2, '+str(value)
        instr_action(self.instr, Query)
    def get_output_source2(self): 
        Li = instr_query(self.instr, 'FPOP? 2').split('\n')[0]
        return int(Li)   
    
    
    def getXoffset_expand(self):
        X1i, X2i = instr_query(self.instr, 'OEXP? 1').split('\n')[0].split(',')
        return float(X1i), int(X2i)
    def getYoffset_expand(self):
        Y1i, Y2i = instr_query(self.instr, 'OEXP? 2').split('\n')[0].split(',')
        return float(Y1i), int(Y2i)
    def getRoffset_expand(self):
        R1i, R2i = instr_query(self.instr, 'OEXP? 3').split('\n')[0].split(',')
        return float(R1i), int(R2i)
    def Xoffset(self, value):
        X1i, X2i = instr_query(self.instr, 'OEXP? 1').split('\n')[0].split(',')
        Query = 'OEXP 1,'+str(value)+', '+X2i
        instr_action(self.instr, Query)
    def Xexpand(self, value):
        X1i, X2i = instr_query(self.instr, 'OEXP? 1').split('\n')[0].split(',')
        Query = 'OEXP 1,'+X1i+', '+str(value)
        instr_action(self.instr, Query) 
    def Xautooffset(self):
        Query = 'AOFF 1'
        instr_action(self.instr, Query)        
    def Yoffset(self, value):
        Y1i, Y2i = instr_query(self.instr, 'OEXP? 2').split('\n')[0].split(',')
        Query = 'OEXP 2,'+str(value)+', '+Y2i
        instr_action(self.instr, Query)
    def Yexpand(self, value):
        Y1i, Y2i = instr_query(self.instr, 'OEXP? 2').split('\n')[0].split(',')
        Query = 'OEXP 2,'+Y1i+', '+str(value)
        instr_action(self.instr, Query)  
    def Yautooffset(self):
        Query = 'AOFF 2'
        instr_action(self.instr, Query)  
    def Roffset(self, value):
        R1i, R2i = instr_query(self.instr, 'OEXP? 3').split('\n')[0].split(',')
        Query = 'OEXP 3,'+str(value)+', '+R2i
        instr_action(Query)
    def Rexpand(self, value):
        R1i, R2i = instr_query(self.instr, 'OEXP? 3').split('\n')[0].split(',')
        Query = 'OEXP 3,'+R1i+', '+str(value)
        instr_action(Query)  
    def Rautooffset(self):
        Query = 'AOFF 3'
        instr_action(self.instr, Query)   

class QHLine(QFrame):
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken) 
 
def swapPositions(list, pos1, pos2):
    list[pos1], list[pos2] = list[pos2], list[pos1]
    return list
         
UNITS = [' encoder count', ' motor step', ' mm', ' \u03BCm', ' in', ' m-in', ' \u03BC-in', '\u00B0', ' g', ' rad', ' mrad', ' \u03BCrad']        
class STAGE(QMainWindow):
    def __init__(self, instr_index, axis_index, CANVAS):
        super().__init__()
        global AXISunits, Xlast;
        self.setWindowTitle("Motion Controller")
        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        self.layout = QtWidgets.QVBoxLayout(self._main) # QtWidgets.QGridLayout(self._main)
        self.setStyleSheet(  GLOBAL_STYLE  )
        self.axis = axis_index
        self.CANVAS = CANVAS
        
        self.instr_index = instr_index
        self.instr = instrSTAGE[instr_index]
        
        # Dlayout = QtWidgets.QVBoxLayout()
        self.var1 = self.read_current_position(); Xlast[self.axis-1] = self.var1
        self.var1f2 = self.read_desired_position(); 
        self.var2 = self.read_axis_displacement_units(); 
        self.var3 = self.read_desired_velocty(); 
        self.var4 = self.read_maximum_allowed_acceleration_deceleration(); 
        self.STOP = True
        self.step_size = 0.2
        
        AXISunits[self.axis-1] = UNITS[self.var2]
        
        Dlabel =  QLabel_(my_style+"<b>AXIS "+str(self.axis)+"</b>");
        # self.sAXIS = QSpinBox_(1, 3, self.axis, self.select_axis)
        DlayoutAS =  QtWidgets.QHBoxLayout();
        if self.axis == 1:
            self.axisP1s = QPushButton_("\u2B9E", self.axisP1); self.axisP1s.setStyleSheet("QPushButton { background:#CFFF00; }")
            DlayoutAS.addWidget(self.axisP1s)
        elif self.axis == 2:
            self.axisM1s = QPushButton_("\u2B9C", self.axisM1); self.axisM1s.setStyleSheet("QPushButton { background:#CFFF00; }")
            self.axisP1s = QPushButton_("\u2B9E", self.axisP1); self.axisP1s.setStyleSheet("QPushButton { background:#CFFF00; }")
            DlayoutAS.addWidget(self.axisM1s); DlayoutAS.addWidget(self.axisP1s); 
        else:
            self.axisM1s = QPushButton_("\u2B9C", self.axisM1); self.axisM1s.setStyleSheet("QPushButton { background:#CFFF00; }")
            DlayoutAS.addWidget(self.axisM1s);        
            
        if self.axis == 1:
            self.AXISlabel = QComboBox_(AXISlabels, 0, self.set_axis_label);
        elif self.axis == 2:
            self.AXISlabel = QComboBox_([lab for lab in AXISlabels if lab != AXISlabels[0]], 0, self.set_axis_label);
        else:
            self.AXISlabel = QComboBox_([lab for lab in AXISlabels if lab != AXISlabels[0] and lab != AXISlabels[1]], 0, self.set_axis_label);
         
        Dlayout =  QtWidgets.QHBoxLayout();
        Dlayout1 = QtWidgets.QVBoxLayout(); Dlayout1.addWidget(Dlabel); Dlayout1.addLayout(DlayoutAS) # Dlayout1.addWidget(self.sAXIS);
        Dlayout.addLayout(Dlayout1); Dlayout.addWidget(self.AXISlabel);
        self.layout.addLayout(Dlayout);

        Dlabel =  QLabel_(""); Dlabel.setFixedHeight(50); self.layout.addWidget(Dlabel);

        Dlayout1 = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Step size</b>");
        self.StepS = QDoubleSpinBox_(0, 1000.00, self.step_size, self.change_step_size, " "+UNITS[self.var2], 0.1)
        for WIDGET in [Dlabel, self.StepS]: Dlayout1.addWidget(WIDGET);
        self.layout.addLayout(Dlayout1)

        Dlayout1 = QtWidgets.QHBoxLayout()
        self.STP = QPushButton_("  STOP  ", self.STOPmotion); self.STP.setStyleSheet("QPushButton { background:#f08f41; }")
        self.toLL = QPushButton_("\u00AB", self.toLeftLeft)
        self.toL = QPushButton_("\u2039", self.toLeft)
        self.toR = QPushButton_("\u203A", self.toRight)
        self.toRR = QPushButton_("\u00BB", self.toRightRight)
        for WIDGET in [self.STP, self.toLL, self.toL, self.toR, self.toRR]: Dlayout1.addWidget(WIDGET);
        self.layout.addLayout(Dlayout1)
        
        self.lower_bound = dictionary[str(self.axis)]['lower_bound'] # 0
        self.upper_bound = dictionary[str(self.axis)]['upper_bound'] # 1000
        
        Dlayout1 = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Lower bound</b>");
        self.LOWERB = QDoubleSpinBox_(-1000, 1000.00, self.lower_bound, self.change_lower_bound, " "+UNITS[self.var2], 0.25)
        for WIDGET in [Dlabel, self.LOWERB]: Dlayout1.addWidget(WIDGET);
        Dlabel =  QLabel_(my_style+"<b>Upper bound</b>");
        self.UPPERB = QDoubleSpinBox_(-1000, 1000.00, self.upper_bound, self.change_upper_bound, " "+UNITS[self.var2], 0.25)
        for WIDGET in [Dlabel, self.UPPERB]: Dlayout1.addWidget(WIDGET);
        self.layout.addLayout(Dlayout1)     
        
        Dlayout1 = QtWidgets.QHBoxLayout()
        self.DlabelP =  QLabel_(my_style+"<b>Current position</b><br>"+str(self.var1)+UNITS[self.var2]);
        self.DlabelDP =  QLabel_(my_style+"<b>Desired position</b><br>"+str(self.var1f2)+UNITS[self.var2]); self.DlabelDP.setAlignment(Qt.AlignCenter); 
        for WIDGET in [self.DlabelP, self.DlabelDP]: Dlayout1.addWidget(WIDGET);
        self.layout.addLayout(Dlayout1)
        
        Dlayout1 = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Set relative motion</b>");
        self.PR = QDoubleSpinBox_(-1000.00, 1000.00, 0, self.start_relative_motion, " "+UNITS[self.var2], 0.1)
        for WIDGET in [Dlabel, self.PR]: Dlayout1.addWidget(WIDGET);
        self.layout.addLayout(Dlayout1)

        Dlayout1 = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Set position</b>");
        self.SETPOS = QDoubleSpinBox_(0.00, 1000.00, 0, self.set_position, " "+UNITS[self.var2], 0.1)
        for WIDGET in [Dlabel, self.SETPOS]: Dlayout1.addWidget(WIDGET);
        self.layout.addLayout(Dlayout1)
        
        Dlayout1 = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Motor</b>"); Dlabel.setFixedWidth(100)
        MOTORONOFF = self.read_motor_on()
        self.toggleMotor = AnimatedToggle(checked_color="#00AA80", pulse_checked_color="#44FFB000")
        self.toggleMotor.clicked.connect(self.turn_motor)
        if MOTORONOFF == 1: self.toggleMotor.setChecked(True)
        else: self.toggleMotor.setChecked(False)
        self.toggleMotor.setText("ON"); self.toggleMotor.setFixedWidth(150)
        self.HOME = QPushButton_("Home Search", self.search_home); self.HOME.setStyleSheet("QPushButton { background:#ff30f8; font-weight: bold;}")
        for WIDGET in [Dlabel, self.toggleMotor]: Dlayout1.addWidget(WIDGET);
        Dlabel =  QLabel_(my_style+""); Dlabel.setFixedWidth(100)
        for WIDGET in [Dlabel, self.HOME]: Dlayout1.addWidget(WIDGET);
        self.layout.addLayout( Dlayout1 )
        
        self.layout.addWidget(QHLine())
        self.DlabelVV =  QLabel_(my_style+"<b>Velocity</b><br>"+str(self.var3)+UNITS[self.var2]+'/s');  
        self.layout.addWidget( self.DlabelVV);  self.layout.addWidget(QHLine());

        Dlabel =  QLabel_(my_style+"<b>Maximum allowed acceleration/deceleration</b><br>"+str(self.var4)+UNITS[self.var2]+'/s<sup>2</sup>'); self.layout.addWidget(Dlabel);   
        Dlayout1 = QtWidgets.QHBoxLayout()
        self.DlabelA =  QLabel_(my_style+"<b>Current acceleration</b> "+str(self.var4)+UNITS[self.var2]+'/s<sup>2</sup>');  
        self.DlabelD =  QLabel_(my_style+"<b>Current deceleration</b> "+str(self.var4)+UNITS[self.var2]+'/s<sup>2</sup>'); 
        for WIDGET in [self.DlabelA, self.DlabelD]: Dlayout1.addWidget(WIDGET);
        self.layout.addLayout(Dlayout1)
        
        Dlayout1 = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Set acceleration</b>");
        self.ACC = QDoubleSpinBox_(0.00, self.var4, 0, self.set_axis_acceleration, " "+UNITS[self.var2]+'/s\u00B2', 0.1)
        for WIDGET in [Dlabel, self.ACC]: Dlayout1.addWidget(WIDGET);

        Dlabel =  QLabel_(my_style+"<b>Set deceleration</b>"); # Dlayout1.addWidget(Dlabel);   
        self.DEC = QDoubleSpinBox_(0.00, self.var4, 0, self.set_axis_acceleration, " "+UNITS[self.var2]+'/s\u00B2', 0.1)
        for WIDGET in [Dlabel, self.DEC]: Dlayout1.addWidget(WIDGET);
        
        self.layout.addLayout(Dlayout1)
        
        Dlayout1 = QtWidgets.QHBoxLayout()
        self.textbox = QTextEdit(); self.textbox.setPlaceholderText("Query...") ;
        self.textbox.setStyleSheet("QTextEdit { background-color : #e4e6e7; font-family: 'Times New Roman'; font-size:35px; }" );
        self.submitQ = QPushButton_("Query", self.send_query); self.submitQ.setStyleSheet("QPushButton { background:#ff30f8; font-weight: bold;}"); self.submitQ.setFixedWidth(100)
        self.submitA = QPushButton_("Action", self.send_action); self.submitA.setStyleSheet("QPushButton { background:#ff30f8; font-weight: bold;}"); self.submitA.setFixedWidth(100)
        for WIDGET in [self.textbox, self.submitQ, self.submitA]: Dlayout1.addWidget(WIDGET);

        self.layout.addLayout(Dlayout1)
        
        self.setLayout(self.layout)
        # self.show()
        
    def send_query(self):
        instructions = self.textbox.toPlainText()
        instructions.replace(" ","")
        if len(instructions) != 0:
            try:
                resp = instr_query( instrSTAGE[0], instructions, False )
                msg = QMessageBox()
                msg.setWindowTitle("Response")
                msg.setText(resp)
                msg.exec_()
                while self.read_motion_done( ) != 1: time.sleep(0.01)
                time.sleep(0.1)
                self.update();
            except:
                msg = QMessageBox()
                msg.setWindowTitle("Response")
                msg.setText("An error occurred")
                msg.exec_()
    def send_action(self):
        instructions = self.textbox.toPlainText()
        instructions.replace(" ","")
        if len(instructions) != 0:
            try:
                instr_action( instrSTAGE[0], instructions, False )
                while self.read_motion_done( ) != 1: time.sleep(0.01)
                time.sleep(0.1)
                self.update();
            except:
                msg = QMessageBox()
                msg.setWindowTitle("Response")
                msg.setText("An error occurred")
                msg.exec_()
                
    def change_lower_bound(self, value):  
        global dictionary
        self.lower_bound = value; 
        dictionary[str(self.axis)]['lower_bound'] = value; update_dictionary()
        
    def change_upper_bound(self, value):  
        global dictionary
        self.upper_bound = value
        dictionary[str(self.axis)]['upper_bound'] = value; update_dictionary()

    def set_axis_label(self, value):
        global AXISlabels, dictionary
        if self.axis == 1:
            COP = AXISlabels.copy()
            AXISlabels[0] = COP[value]; AXISlabels[value] = COP[0];
            STAGE_AXES[0].AXISlabel.blockSignals(True); STAGE_AXES[0].AXISlabel.clear(); STAGE_AXES[0].AXISlabel.addItems(AXISlabels);      STAGE_AXES[0].AXISlabel.setCurrentIndex(0);  STAGE_AXES[0].AXISlabel.blockSignals(False);
            STAGE_AXES[1].AXISlabel.blockSignals(True); STAGE_AXES[1].AXISlabel.clear(); STAGE_AXES[1].AXISlabel.addItems(AXISlabels[1:]);  STAGE_AXES[1].AXISlabel.setCurrentIndex(0);  STAGE_AXES[1].AXISlabel.blockSignals(False);
            STAGE_AXES[2].AXISlabel.blockSignals(True); STAGE_AXES[2].AXISlabel.clear(); STAGE_AXES[2].AXISlabel.addItems(AXISlabels[2:]);  STAGE_AXES[2].AXISlabel.setCurrentIndex(0);  STAGE_AXES[2].AXISlabel.blockSignals(False);
            for i in ['1','2','3']: dictionary[i]['label'] = AXISlabels[int(i)-1]
            update_dictionary(); mySCAN.update()
                
        elif self.axis == 2:
            COP = AXISlabels.copy()
            AXISlabels[1] = COP[value+1]; AXISlabels[value+1] = COP[1];
            STAGE_AXES[0].AXISlabel.blockSignals(True); STAGE_AXES[0].AXISlabel.clear(); STAGE_AXES[0].AXISlabel.addItems(AXISlabels);      STAGE_AXES[0].AXISlabel.setCurrentIndex(0);  STAGE_AXES[0].AXISlabel.blockSignals(False);
            STAGE_AXES[1].AXISlabel.blockSignals(True); STAGE_AXES[1].AXISlabel.clear(); STAGE_AXES[1].AXISlabel.addItems(AXISlabels[1:]);  STAGE_AXES[1].AXISlabel.setCurrentIndex(0);  STAGE_AXES[1].AXISlabel.blockSignals(False);
            STAGE_AXES[2].AXISlabel.blockSignals(True); STAGE_AXES[2].AXISlabel.clear(); STAGE_AXES[2].AXISlabel.addItems(AXISlabels[2:]);  STAGE_AXES[2].AXISlabel.setCurrentIndex(0);  STAGE_AXES[2].AXISlabel.blockSignals(False);
            for i in ['1','2','3']: dictionary[i]['label'] = AXISlabels[int(i)-1]
            update_dictionary(); mySCAN.update()
    def read_motor_on(self):
        return instr_query(self.instr, str(self.axis)+'MO?', type=int)
    def turn_motor(self, value):
        if value:  instr_action(self.instr, str(self.axis)+'MO')
        else:  instr_action(self.instr, str(self.axis)+'MF')
    def search_home(self): 
        instr_action(self.instr, str(self.axis)+'OR0')
        while self.read_motion_done( ) != 1: time.sleep(0.1)
        time.sleep(0.1)
        self.update();
        dictionary[str(self.axis)]['home'] = self.var1; update_dictionary()
    def read_motion_done(self):
        return instr_query(self.instr, str(self.axis)+'MD?', type=int)
    def change_step_size(self, value): self.step_size = value
    def STOPmotion(self): self.STOP = True
    def toLeftLeft(self):
        self.STOP = False; 
        while not self.STOP:
            self.start_relative_motion(-self.step_size, updatePanel=True); # time.sleep(0.01); self.update();
            cv2.waitKey(20)
    def toLeft(self): self.start_relative_motion(-self.step_size, updatePanel=True);
    def toRight(self): self.start_relative_motion(+self.step_size, updatePanel=True);
    def toRightRight(self):
        self.STOP = False; 
        while not self.STOP:
            self.start_relative_motion(+self.step_size, updatePanel=True); # time.sleep(0.01); self.update();
            cv2.waitKey(20)
    def axisM1(self):
        self.hide(); STAGE_AXES[self.axis-2].show()
    def axisP1(self):
        self.hide(); STAGE_AXES[self.axis].show()
    def select_axis(self, value):
        self.hide(); #self.sAXIS.setValue(self.axis)
        STAGE_AXES[value-1].show() #self.__init__(self.instr_index , value, self.CANVAS)
        # self.show()
    def update(self, updatePlot = True, updatePanel = False, XY = 2):
        global Xvalues, Yvalues, Y2values, Xlast;

        self.var1 = self.read_current_position(); # time.sleep(0.1)
        
        if updatePlot: 
            Xlast = [ STAGE_AXES[0].var1, STAGE_AXES[1].var1, STAGE_AXES[2].var1  ]
            Xvalues.append(Xlast); 
            time.sleep(  max(TIMEconstants)  )
            Yvalues.append(getOUTP(instrLOCKIN[0], XY));  # 2
            if NinstrLOCKIN>1: Y2values.append(getOUTP(instrLOCKIN[1],2)); 
            #self.CANVAS._update_canvas_() # Xvalues.append(self.var1); getOUTP(instrLOCKIN[0],1)

        #self.var3 = self.read_desired_velocty(); 
        #self.var1f2 = self.read_desired_position(); 
        
        #self.DlabelDP.setText(my_style+"<b>Desired position</b><br>"+str(self.var1f2)+UNITS[self.var2]);
        if updatePanel:
            self.DlabelDP.setText(my_style+"<b>Desired position</b><br>"+str(self.var1)+UNITS[self.var2]);
            self.DlabelP.setText(my_style+"<b>Current position</b><br>"+str(self.var1)+UNITS[self.var2]);
        #self.DlabelVV.setText(my_style+"<b>Velocity</b><br>"+str(self.var3)+UNITS[self.var2]+'/s');      
    def  set_axis_acceleration(self, target):
        if target<=self.var4:
            instr_action(self.instr, str(self.axis)+'AC'+str(target))
    def  set_axis_deceleration(self, target):
        if target<=self.var4:
            instr_action(self.instr, str(self.axis)+'AG'+str(target))
    def set_position(self, target, updatePlot=True, sleep=0.3, XY = 0):
        #self.start_relative_motion( np.round(target-self.var1,6), updatePlot, sleep )
        
        #if target <= self.upper_bound and target >= self.lower_bound:
            instr_action(self.instr, str(self.axis)+'PA'+str(target));
            time.sleep(sleep)
            while self.read_motion_done( ) != 1: time.sleep(sleep); # cv2.waitKey(20);  time.sleep(0.1);
            time.sleep(sleep)
            self.update(updatePlot, XY = XY);
            
    def start_relative_motion(self, target, updatePlot=True, sleep=0.3, updatePanel=False): 
        self.PR.setEnabled(False)
        if target + self.var1 <= self.upper_bound and target + self.var1 >= self.lower_bound:
            instr_action(self.instr, str(self.axis)+'PR'+str(target));
            time.sleep(0.01)
            while self.read_motion_done( ) != 1: cv2.waitKey(20); time.sleep(0.1)
            time.sleep(sleep)
            self.update(updatePlot, updatePanel);
        self.PR.setEnabled(True)
        
    def start_group_relative_motion(self, axes, motion, updatePlot=True, sleep=0.3 ):
        for i in range(len(axes)-1):
            STAGE_AXES[int(axes[i])-1].start_relative_motion( motion, updatePlot=False, sleep=sleep  )
        STAGE_AXES[int(axes[-1])-1].start_relative_motion( motion, updatePlot, sleep=sleep  )
    def set_group_position(self, axes, motions, updatePlot=True, sleep=0.3 ):
        for i in range(len(axes)-1):
            STAGE_AXES[int(axes[i])-1].set_position( motions[ int(axes[i])-1 ], updatePlot=False, sleep=sleep  )
        STAGE_AXES[int(axes[-1])-1].set_position( motions[ int(axes[-1])-1 ], updatePlot, sleep=sleep  )

    def read_current_position(self):
        return instr_query(self.instr, str(self.axis)+'TP?', type=float)
    def read_desired_position(self):
        return instr_query(self.instr, str(self.axis)+'DP?', type=float)
    def read_desired_velocty(self):
        return instr_query(self.instr, str(self.axis)+'DV', type=float)
    def read_axis_displacement_units(self):
        return instr_query(self.instr, str(self.axis)+'SN?', type=int)
    def set_axis_displacement_units(self, target):
        instr_action(self.instr, str(self.axis)+'SN'+str(target))
    def read_maximum_allowed_acceleration_deceleration(self):
        return instr_query(self.instr, str(self.axis)+'AU?', type=float)   
    def read_current_acceleration(self):
        return instr_query(self.instr, str(self.axis)+'AC?', type=float)
    def read_current_deceleration(self):
        return instr_query(self.instr, str(self.axis)+'AG?', type=float)


class MyFigureCanvas(FigureCanvas):
    def __init__(self) -> None:
        super().__init__(mpl.figure.Figure())

        self.ax = self.figure.subplots()
        self.ax.set_xlabel('Position [nm]', fontsize=30);
        self.ax.set_ylabel('$V_1$ [V]', fontsize=30);
        self.ax.yaxis.label.set_color('red')
        
        if NinstrLOCKIN > 1:
            self.ax2 = self.ax.twinx()
            self.ax2.set_ylabel('$V_2$ [V]', fontsize=30);
            self.ax2.yaxis.label.set_color('blue')
            self.ax2.yaxis.get_offset_text().set_fontsize(24)

            
        self.ax.yaxis.get_offset_text().set_fontsize(24)

        self.to_plot = 0; self.distance_time = 0;
        
        self.ax.tick_params(axis='both', which='major', labelsize=20)
        self.ax.tick_params(axis='both', which='minor', labelsize=20)
        self.ax.patch.set_facecolor('white'); self.ax.patch.set_alpha(0.1)
        self.ax.grid(); 

        self.line1, = self.ax.plot([], [], '-ro', markersize=3);
        self.line2, = self.ax.plot([], [], 'or', markersize=12);
        self.line3, = self.ax.plot([], [], '-bo', markersize=3);
        self.line4, = self.ax.plot([], [], 'ob', markersize=12);
        
        self.draw()
        return
    
    # getOUTP(2)
    def _update_canvas_(self) -> None:
        global Xvalues, Yvalues, Y2values, Xlast;
        while continue_plot:
            if self.distance_time == 0: self.ax.set_xlabel('Position [nm]', fontsize=30);
            elif self.distance_time == 1:   self.ax.set_xlabel('Time [ps]', fontsize=30);
            try:

                if Xvalues[-1] in Xvalues[0:-1]:
                    position_index = Xvalues.index(Xvalues[-1])
                    Yvalues[ position_index ] = (Yvalues[ position_index ] +  Yvalues[-1])/2
                    if NinstrLOCKIN>1:
                        Y2values[ position_index ] = (Y2values[ position_index ] +  Y2values[-1])/2
                        del Y2values[-1]; 
                    del Xvalues[-1]; del Yvalues[-1]; 
                    
                xs = [i[self.to_plot] for i in Xvalues]
                xs, ys = zip(*sorted(zip(xs, Yvalues)))
                xs = np.array(xs)
                if self.distance_time == 1: xs = (xs-mySCAN.AXP0[self.to_plot])*2e9*mySCAN.fac/mySCAN.C
                self.line1.set_data(xs, ys);
               
                if NinstrLOCKIN > 1:
                    xs, ys = zip(*sorted(zip(Xvalues[self.to_plot], Y2values)))
                    if self.distance_time == 1: xs = (xs-mySCAN.AXP0[self.to_plot])*2e9*mySCAN.fac/mySCAN.C
                    self.line3.set_data(xs, ys);
                    self.ax2.relim(); self.ax2.autoscale_view()

                self.ax.relim(); self.ax.autoscale_view()
                self.draw()
                time.sleep(0.3)
            except: time.sleep(0.3)

        
    def background_update(self):
        global Y1last, Y2last;
        while continue_background:
            try:
                Y1last = getOUTP(instrLOCKIN[0], 2, rep=False)
                if self.distance_time == 0: self.line2.set_data([Xlast[self.to_plot]], [Y1last]);
                elif self.distance_time == 1: self.line2.set_data([Xlast[self.to_plot]*2e6*mySCAN.fac/mySCAN.C], [Y1last]);
                self.ax.relim(); self.ax.autoscale_view()
            except: pass
    
            if NinstrLOCKIN>1:
                try:
                    Y2last = getOUTP(instrLOCKIN[1],2 , rep=False)
                    if self.distance_time == 0: self.line4.set_data([Xlast[-1]], [Y2last]);
                    if self.distance_time == 1: self.line4.set_data([Xlast[-1]*2e6*mySCAN.fac/mySCAN.C], [Y2last]);
                    self.ax2.relim(); self.ax2.autoscale_view()
                except: pass
            self.draw()
            time.sleep(0.3)
    


def findOccurrences(s, ch):
    return [i for i, letter in enumerate(s) if letter == ch]


def check_if_in_dictionary(dictionary, *val):
    N = len(val)
    try:
        if N==1: dictionary[val[0]]; return True
        elif N==2:  dictionary[val[0]][val[1]]; return True
        elif N==3:  dictionary[val[0]][val[1]][val[2]]; return True
        elif N==4:  dictionary[val[0]][val[1]][val[2]][val[3]]; return True
    except:
        return False

########## class SCAN
class SCAN(QMainWindow):
    def __init__(self, parent):
        super().__init__()
        self.setWindowTitle("Scanning")
        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        self.layout = QtWidgets.QGridLayout(self._main)
        self.setStyleSheet(  GLOBAL_STYLE  )
        
        
        #qtRectangle = self.frameGeometry()
        #centerPoint = QDesktopWidget().availableGeometry().center()
        #qtRectangle.moveCenter(centerPoint)
        #self.move(qtRectangle.topRight())
        self.move(500, 0)
        
        self.AXISlist = STAGE_AXES;
        
        self.parent = parent
        self.C = 299792458
        self.STEPSIZE = 1
        self.Nruns = 1
        self.Nsteps = 10
        self.fac = -1
        self.STOPscan = False
        self.file_extension = 'json'
        
        self.AX1p0 = dictionary['1']['p0']
        self.AX2p0 = dictionary['2']['p0']
        self.AX3p0 = dictionary['3']['p0']
        self.AXP0 = [ self.AX1p0, self.AX2p0, self.AX3p0  ] 
        
        self.AX1off = dictionary['1']['off']
        self.AX2off = dictionary['2']['off']
        self.AX3off = dictionary['3']['off']
        self.AXOFF = [ self.AX1off, self.AX2off, self.AX3off  ]
        
        self.measureXY = 1
        
        Dlayout1 = QtWidgets.QHBoxLayout()
        Dlayout = QtWidgets.QVBoxLayout()
        Dlabel =  QLabel_(my_style2+"<b>Axis</b>");   self.layout.addWidget(Dlabel, 0, 0, 1, 1)
        self.DlabelAX1 =  QLabel_(my_style + '<b>1</b>: ' + dictionary['1']['label'] ); #self.layout.addWidget(self.DlabelAX1, 1, 0, 1, 1)
        self.DlabelAX2 =  QLabel_(my_style + '<b>2</b>: ' + dictionary['2']['label'] ); #self.layout.addWidget(self.DlabelAX2, 2, 0, 1, 1)
        self.DlabelAX3 =  QLabel_(my_style + '<b>3</b>: ' + dictionary['3']['label'] ); #self.layout.addWidget(self.DlabelAX3, 3, 0, 1, 1)
        for WIDGET in [Dlabel, self.DlabelAX1, self.DlabelAX2, self.DlabelAX3]: Dlayout.addWidget(WIDGET)
        Dlayout1.addLayout(Dlayout)
        
        Dlayout = QtWidgets.QVBoxLayout()
        Dlabel =  QLabel_(my_style2+"<b>0ps position</b>");
        self.P0current = QPushButton_("Use current\npositions", self.set_p0_current); 
        Dlayout0 = QtWidgets.QHBoxLayout()
        Dlayout0.addWidget(Dlabel); Dlayout0.addWidget(self.P0current); 
        self.AX1pos = QDoubleSpinBox_(-1000.00, 1000, self.AX1p0, self.set_AX1_pos0, " "+AXISunits[0], 0.1); #self.layout.addWidget(self.AX1pos, 1, 1, 1, 1)
        self.AX2pos = QDoubleSpinBox_(-1000.00, 1000, self.AX2p0, self.set_AX2_pos0, " "+AXISunits[1], 0.1); #self.layout.addWidget(self.AX2pos, 2, 1, 1, 1)
        self.AX3pos = QDoubleSpinBox_(-1000.00, 1000, self.AX3p0, self.set_AX3_pos0, " "+AXISunits[2], 0.1); #self.layout.addWidget(self.AX3pos, 3, 1, 1, 1)
        for WIDGET in [Dlayout0, self.AX1pos, self.AX2pos, self.AX3pos]: addWidLay(Dlayout, WIDGET); # Dlayout.addWidget(WIDGET)
        Dlayout1.addLayout(Dlayout)
        
        Dlayout = QtWidgets.QVBoxLayout()
        Dlabel =  QLabel_(my_style2+"<b>Prescan</b>");
        self.AX1offset = QDoubleSpinBox_(-1000, 1000, self.AX1off, self.set_AX1_off, " "+AXISunits[0], 0.1); #self.layout.addWidget(self.AX1offset, 1, 2, 1, 1)
        self.AX2offset = QDoubleSpinBox_(-1000, 1000, self.AX2off, self.set_AX2_off, " "+AXISunits[1], 0.1); #self.layout.addWidget(self.AX2offset, 2, 2, 1, 1)
        self.AX3offset = QDoubleSpinBox_(-1000, 1000, self.AX3off, self.set_AX3_off, " "+AXISunits[2], 0.1); #self.layout.addWidget(self.AX3offset, 3, 2, 1, 1)
        for WIDGET in [Dlabel, self.AX1offset, self.AX2offset, self.AX3offset]: Dlayout.addWidget(WIDGET)
        Dlayout1.addLayout(Dlayout)
        self.layout.addLayout(Dlayout1, 0, 0, 3, 3)

        Dlabel =  QLabel_(""); Dlabel.setFixedHeight(50);
        self.layout.addWidget(Dlabel, 4, 0, 1, 3)
        
        Dlayout = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Step size</b>"); Dlayout.addWidget(Dlabel)
        self.STEPSIZEs = QDoubleSpinBox_(0.00, 1000, self.STEPSIZE, self.set_step_size, " \u03BCm", 0.1); Dlayout.addWidget(self.STEPSIZEs)
        Dlabel =  QLabel_(""); Dlabel.setFixedWidth(50); Dlayout.addWidget(Dlabel)
        self.LabelPS =  QLabel_(my_style+"<b><i>dt</i></b> = " + str(np.round(2*1e6/self.C, 3)) +" ps"); Dlayout.addWidget(self.LabelPS)
        Dlabel =  QLabel_(""); Dlabel.setFixedWidth(50); Dlayout.addWidget(Dlabel)

        self.layout.addLayout(Dlayout, 5, 0, 1, 3)
        self.layout.addWidget(QHLine(), 6, 0, 1, 3)

        Dlayout = QtWidgets.QHBoxLayout()
        #Dlabel =  QLabel_(my_style+"<b># Rounds</b>"); Dlayout.addWidget(Dlabel)
        self.NRUNs = QLSpinBox_(my_style+"<b># Rounds</b>", 1, 1000, self.Nruns, self.set_number_runs); # Dlayout.addWidget(self.NRUNs)
        # Dlabel =  QLabel_(""); Dlabel.setFixedWidth(50); Dlayout.addWidget(Dlabel)
        # Dlabel =  QLabel_(my_style+"<b># Steps</b>"); Dlayout.addWidget(Dlabel)
        self.NSTEPSs = QLSpinBox_(my_style+"<b># Steps</b>", 1, 1000, self.Nsteps, self.set_number_steps); # Dlayout.addWidget(self.NSTEPSs)
        self.VXY =  QLQComboBox_(my_style+"<b>Measure</b>", ["X", "Y"], self.measureXY, self.set_measureXY); 
        for WIDGET in [self.NRUNs, self.NSTEPSs, self.VXY]: addWidLay(Dlayout, WIDGET)
        
        self.layout.addLayout(Dlayout, 7, 0, 1, 3)
        Dlabel =  QLabel_(""); Dlabel.setFixedHeight(50);
        self.layout.addWidget(Dlabel, 8, 0, 1, 3)
        
        ### Options to Scan Language
        self.moveAX1 = False; self.moveAX2 = False; self.moveAX3 = False
        self.moveAX1p0 = False; self.moveAX2p0 = False; self.moveAX3p0 = False
        self.use_final_position = False;
        self.axes_changed = False;
        
        self.INSERTscan = QtWidgets.QHBoxLayout()
        Dlayout = QtWidgets.QVBoxLayout()
        Dlayout1 = QtWidgets.QHBoxLayout(); Dlabel =  QLabel_(my_style+"<b>Move Axis 1</b>");
        self.MA1 = QCheckBox(); self.MA1.clicked.connect(self.check_moveAX1)
        self.MA1p0 =  QPushButton_("Just to 0ps position", self.check_moveAX1p0);  self.MA1p0.setStyleSheet("QPushButton { background:#6b806c; font-weight: bold; font-size: 20px}")
        for WIDGET in [Dlabel, self.MA1, self.MA1p0 ]: Dlayout1.addWidget(WIDGET)
        Dlayout.addLayout(Dlayout1)
        Dlayout1 = QtWidgets.QHBoxLayout(); Dlabel =  QLabel_(my_style+"<b>Move Axis 2</b>");
        self.MA2 = QCheckBox(); self.MA2.clicked.connect(self.check_moveAX2)
        self.MA2p0 =  QPushButton_("Just to 0ps position", self.check_moveAX2p0);  self.MA2p0.setStyleSheet("QPushButton { background:#6b806c; font-weight: bold; font-size: 20px}")
        for WIDGET in [Dlabel, self.MA2, self.MA2p0 ]: Dlayout1.addWidget(WIDGET)
        Dlayout.addLayout(Dlayout1)
        Dlayout1 = QtWidgets.QHBoxLayout(); Dlabel =  QLabel_(my_style+"<b>Move Axis 3</b>");
        self.MA3 = QCheckBox(); self.MA3.clicked.connect(self.check_moveAX3)
        self.MA3p0 =  QPushButton_("Just to 0ps position", self.check_moveAX3p0);  self.MA3p0.setStyleSheet("QPushButton { background:#6b806c; font-weight: bold; font-size: 20px}")
        for WIDGET in [Dlabel, self.MA3, self.MA3p0 ]: Dlayout1.addWidget(WIDGET)
        Dlayout.addLayout(Dlayout1); 
        self.INSERTscan.addLayout(Dlayout)
        
        Dlabel =  QLabel_(""); Dlabel.setFixedWidth(50); self.INSERTscan.addWidget(Dlabel)
        
        Dlayout = QtWidgets.QVBoxLayout();
        Dlabel =  QLabel_(my_style+"<b>Starting position</b>");
        self.INITIALp0 = QDoubleSpinBox_(-1000, 1000, 0, None, " ps", 0.1);
        for WIDGET in [Dlabel, self.INITIALp0]: Dlayout.addWidget(WIDGET)
        self.INSERTscan.addLayout(Dlayout)
        
        Dlabel =  QLabel_(""); Dlabel.setFixedWidth(50)
        self.INSERTscan.addWidget(Dlabel)
        
        Dlayout = QtWidgets.QVBoxLayout();
        self.FINALp =  QPushButton_("Set Final Position", self.check_final);  self.FINALp.setStyleSheet("QPushButton { background:#6b806c; font-weight: bold; font-size: 20px}")
        #Dlabel =  QLabel_(my_style+"<b>Ending position</b>");
        self.FINALp0 = QDoubleSpinBox_(-1000, 1000, 0, None, " ps", 0.1);
        for WIDGET in [self.FINALp, self.FINALp0]: Dlayout.addWidget(WIDGET)
        self.INSERTscan.addLayout(Dlayout)
        
        Dlabel =  QLabel_(my_style+"<i>  OR  </i>");
        self.USEsteps =  QPushButton_("Use # Steps", self.check_final);  self.USEsteps.setStyleSheet("QPushButton { background:#1bf726; font-weight: bold; font-size: 20px}")
        for WIDGET in [Dlabel, self.USEsteps]: self.INSERTscan.addWidget(WIDGET)
        
        Dlabel =  QLabel_(""); Dlabel.setFixedWidth(50); self.INSERTscan.addWidget(Dlabel)

        Dlayout = QtWidgets.QVBoxLayout();
        Dlabel =  QLabel_(my_style+"<b>Repetitions</b>");
        self.SCANrep = QSpinBox_(1, 1000, 1);
        for WIDGET in [Dlabel, self.SCANrep]: Dlayout.addWidget(WIDGET)
        self.INSERTscan.addLayout(Dlayout)

        self.layout.addLayout(self.INSERTscan, 9, 0, 1, 2)
        self.TOscan =  QPushButton_("\uFFEC INSERT \uFFEC", self.insert_scan);  self.TOscan.setStyleSheet("QPushButton { background:#19d5e9; font-weight: bold; font-size: 25px}")
        self.layout.addWidget(self.TOscan, 10, 0, 1, 2)
        ###
        
        self.textbox = QTextEdit(); self.textbox.setPlaceholderText("""Scanning Instructions... (e.g., \n23: -1>/5 <0/3 to move axes 2 and 3, from position -1 to the right # steps (5 times), and then to move them from position 0 to the left # steps (3 times)).
        a>b/n will move the axis from position a to position b (n times);
        a<b/n will move the axis from position b to position a (n times);
        a<>b/n will move the axis from position a to position b and back (n times);
     \nBy default, a>/n can be specified simply as a/n.\n/n indicates that the move will be repeated n times; if /n is not indicated, the move will be made only once.""") ;
        self.textbox.setStyleSheet("QTextEdit { background-color : #e4e6e7; font-family: 'Times New Roman'; font-size:25px; }" );
        self.textbox.setFixedHeight(200); self.textbox.setFixedWidth(1200) #self.textbox.resize(280,40)
        Dlayout = QtWidgets.QVBoxLayout()
        self.DIR = QPushButton_("dx \u2192 \n dt \u2190", self.change_dir); self.DIR.setStyleSheet("QPushButton { background:#f0cd1f; font-weight: bold; font-size: 47px}")
        self.DIR.setFixedHeight(100);
        self.RUN = QPushButton_("RUN", self.start_scan); self.RUN.setStyleSheet("QPushButton { background:#E10000; font-weight: bold; font-size: 60px}")
        self.RUN.setFixedHeight(200);
        self.STOPmySCAN = QPushButton_("STOP", self.stop_scan); self.STOPmySCAN.setStyleSheet("QPushButton { background:#E10000; font-weight: bold; font-size: 60px}")
        self.STOPmySCAN.setFixedHeight(100);
        Dlayout.addWidget(self.DIR); Dlayout.addWidget(self.RUN); Dlayout.addWidget(self.STOPmySCAN); 
        self.layout.addWidget(self.textbox, 11, 0, 6, 2)
        self.layout.addLayout(Dlayout, 9, 2, 8, 1)

        self.layout.setRowStretch(6, 5) ; self.layout.setColumnStretch(0, 2);  self.layout.setColumnStretch(1, 1);
        
        Dlayout = QtWidgets.QHBoxLayout()
        self.demo = Demo(0); self.demo.setFixedWidth(500); Dlayout.addWidget(self.demo); 
        Dlabel =  QLabel_(my_style+"<b>File Extension</b>")
        self.FILEext = QComboBox_([".json", ".txt"], 0, self.set_file_extension); 
        for WIDGET in [Dlabel,  self.FILEext]: Dlayout.addWidget(WIDGET);
        self.layout.addLayout(Dlayout, 18, 0, 1, 3)

        self.setLayout(self.layout)
       
    def set_measureXY(self, value): self.measureXY = value
        
    def insert_scan(self):
        new_instruction = ''
        if self.moveAX1 or self.moveAX2 or self.moveAX3:
            if self.moveAX1 and not self.moveAX1p0: new_instruction += '1'
            if self.moveAX2 and not self.moveAX2p0: new_instruction += '2'
            if self.moveAX3 and not self.moveAX3p0: new_instruction += '3'
            if self.moveAX1p0 or self.moveAX2p0 or self.moveAX3p0:
                new_instruction += '_'
            if self.moveAX1 and self.moveAX1p0: new_instruction += '1'
            if self.moveAX2 and self.moveAX2p0: new_instruction += '2'
            if self.moveAX3 and self.moveAX3p0: new_instruction += '3'
            new_instruction += ': ' + str(self.INITIALp0.value())
            if self.use_final_position: new_instruction += '>' + str(self.FINALp0.value())
            new_instruction += '/' + str(self.SCANrep.value())
            
            if self.textbox.toPlainText().replace(" ", "") == '':
                self.textbox.setText( new_instruction )
            else:
                self.textbox.setText( (self.textbox.toPlainText()) + '\n' + new_instruction )

    def check_final(self):
        if not self.use_final_position: 
            self.use_final_position = True; 
            self.FINALp.setStyleSheet("QPushButton { background:#1bf726; font-weight: bold; font-size: 20px}")
            self.USEsteps.setStyleSheet("QPushButton { background:#6b806c; font-weight: bold; font-size: 20px}")
        else:
            self.use_final_position = False;    
            self.FINALp.setStyleSheet("QPushButton { background:#6b806c; font-weight: bold; font-size: 20px}")
            self.USEsteps.setStyleSheet("QPushButton { background:#1bf726; font-weight: bold; font-size: 20px}")

    def check_moveAX1(self):  self.moveAX1 = True if self.MA1.isChecked() else False 
    def check_moveAX2(self):  self.moveAX2 = True if self.MA2.isChecked() else False 
    def check_moveAX3(self):  self.moveAX3 = True if self.MA3.isChecked() else False 
    
    def check_moveAX1p0(self):  
        if not self.moveAX1p0: 
            self.moveAX1p0 = True; self.MA1p0.setStyleSheet("QPushButton { background:#1bf726; font-weight: bold; font-size: 20px}")
        else:
            self.moveAX1p0 = False; self.MA1p0.setStyleSheet("QPushButton { background:#6b806c; font-weight: bold; font-size: 20px}")  
    def check_moveAX2p0(self):  
        if not self.moveAX2p0: 
            self.moveAX2p0 = True; self.MA2p0.setStyleSheet("QPushButton { background:#1bf726; font-weight: bold; font-size: 20px}")
        else:
            self.moveAX2p0 = False; self.MA2p0.setStyleSheet("QPushButton { background:#6b806c; font-weight: bold; font-size: 20px}")  
    def check_moveAX3p0(self):  
        if not self.moveAX3p0: 
            self.moveAX3p0 = True; self.MA3p0.setStyleSheet("QPushButton { background:#1bf726; font-weight: bold; font-size: 20px}")
        else:
            self.moveAX3p0 = False; self.MA3p0.setStyleSheet("QPushButton { background:#6b806c; font-weight: bold; font-size: 20px}")  
            
    def set_p0_current(self):
        for i in range(3): self.AXP0[i] = STAGE_AXES[i].var1; 
        self.AX1pos.setValue(self.AXP0[0]); self.AX2pos.setValue(self.AXP0[1]); self.AX3pos.setValue(self.AXP0[2]);
        dictionary['1']['p0'] = self.AXP0[0];  dictionary['2']['p0'] = self.AXP0[1]; dictionary['3']['p0'] = self.AXP0[2]; 
        update_dictionary()
        
    def set_file_extension(self, value): self.file_extension = 'json' if value==0 else 'txt'
    
    def stop_scan(self):
        if not self.STOPscan:
            self.STOPscan = True 
            self.STOPmySCAN.setText("RESUME"); self.STOPmySCAN.setStyleSheet("QPushButton { background:#3aeb34; font-weight: bold; font-size: 40px}")
        else:
            self.STOPscan = False
            self.STOPmySCAN.setText("STOP"); self.STOPmySCAN.setStyleSheet("QPushButton { background:#E10000; font-weight: bold; font-size: 60px}")           
        
    def change_dir(self): 
        if self.fac == +1:
            self.fac = -1; self.DIR.setText("dx \u2192 \n dt \u2190")
        else:
            self.fac = +1; self.DIR.setText("dx \u2192 \n dt \u2192")

    def update(self):
        self.DlabelAX1.setText(my_style + '<b>1</b>: ' + dictionary['1']['label'] )
        self.DlabelAX2.setText(my_style + '<b>2</b>: ' + dictionary['2']['label'] )
        self.DlabelAX3.setText(my_style + '<b>3</b>: ' + dictionary['3']['label'] )

        # self.DlabelTHZ.setText(my_style+"<b>Axis </b>"+str(self.THZaxis+1));
        # self.DlabelGATE.setText(my_style+"<b>Axis </b>"+str(self.GATEaxis+1));
        # self.THZpos.blockSignals(True); self.THZpos.setValue(self.AXISlist[self.THZaxis].var1);  self.THZpos.blockSignals(False);
        # self.GATEpos.blockSignals(True); self.GATEpos.setValue(self.AXISlist[self.GATEaxis].var1);  self.GATEpos.blockSignals(False);

    def set_AX1_pos0(self,  value): self.AX1p0  = value; self.AXP0 = [ self.AX1p0, self.AX2p0, self.AX3p0  ]; dictionary['1']['p0'] = value; update_dictionary()
    def set_AX2_pos0(self,  value): self.AX2p0  = value; self.AXP0 = [ self.AX1p0, self.AX2p0, self.AX3p0  ]; dictionary['2']['p0'] = value; update_dictionary()
    def set_AX3_pos0(self,  value): self.AX3p0  = value; self.AXP0 = [ self.AX1p0, self.AX2p0, self.AX3p0  ]; dictionary['3']['p0'] = value; update_dictionary()
     
    def set_AX1_off(self,  value): self.AX1off  = value; self.AXOFF = [ self.AX1off, self.AX2off, self.AX3off  ]; dictionary['1']['off'] = value; update_dictionary()
    def set_AX2_off(self,  value): self.AX2off  = value; self.AXOFF = [ self.AX1off, self.AX2off, self.AX3off  ]; dictionary['2']['off'] = value; update_dictionary()
    def set_AX3_off(self,  value): self.AX3off  = value; self.AXOFF = [ self.AX1off, self.AX2off, self.AX3off  ]; dictionary['3']['off'] = value; update_dictionary()

    def set_GATE_pos(self, value):
        current_position = self.AXISlist[self.GATEaxis].var1
        diff = value - current_position
        self.AXISlist[self.GATEaxis].start_relative_motion(diff)
    def set_step_size(self, value): 
        self.STEPSIZE = value 
        self.LabelPS.setText(my_style+"<b><i>dt</i></b> = " + str(np.round(2*value*1e6/self.C, 3)) +" ps")
        
    def set_number_steps(self, value): self.Nsteps = value
    def set_number_runs(self, value): self.Nruns = value
    
    def initial_final(self, instruction):
        initial = ''; final = ''; go_back = False
        
        time_distance_from_steps = self.Nsteps*self.STEPSIZE*2e6/self.C
        
        if '<>' in instruction:
            go_back = True
            initial_, final_ = instruction.split('<>'); 
            if final_ == '':
                initial = float(initial_)
                final = initial + time_distance_from_steps
            elif initial_ ==  '':
                initial = float(final_)
                final = initial - time_distance_from_steps
            else:
                initial = float(initial_); final = float(final_)
        elif '<' in instruction:
            initial_, final_ = instruction.split('<'); 
            if final_ == '':
                final = float(initial_)
                initial = final + time_distance_from_steps
            elif initial_ ==  '':
                initial = float(final_)
                final = initial - time_distance_from_steps
            else:
                initial = float(final_); final = float(initial_)
        elif '>' in instruction:
            initial_, final_ = instruction.split('>');
            if final_ == '':
                initial = float(initial_)
                final = initial + time_distance_from_steps
            elif initial_ ==  '':
                final = float(final_)
                initial = final - time_distance_from_steps
            else:
                initial = float(initial_); final = float(final_)
        else:
            initial = float(instruction)
            final = initial + time_distance_from_steps

        return float(initial), final, go_back
    def start_scan(self):
        self.RUN.setEnabled(False);
        self.parent.pushButton.setEnabled(False);
        self.parent.pushButton2.setEnabled(False);
        self.P0current.setEnabled(False);
        self.AX1pos.setEnabled(False); self.AX2pos.setEnabled(False); self.AX3pos.setEnabled(False);
        self.AX1offset.setEnabled(False);  self.AX2offset.setEnabled(False);  self.AX3offset.setEnabled(False);
        
        def scan_function():
            try:
                start_time = time.time()
                global Xvalues, Yvalues, Y2values, dir_name;
                Xvalues = []; Yvalues = []; Y2values = [];
                STEPSIZEmm = np.round( self.STEPSIZE/1000, 6) # /1000 # um -> mm
                this_measureXY = self.measureXY + 1
                instructions = (self.textbox.toPlainText()).split('\n');
                scan_dictionary = {"Step Size": STEPSIZEmm, "+-1": self.fac, "AX1 center": self.AX1p0, "AX2 center": self.AX2p0, "AX3 center": self.AX3p0}
                
                now = datetime.now(); 
                file_to_save = "RUN_" + now.strftime("%m-%d-%Y-%H-%M") + ".json"
                
                ax_instructions = []; ax = [];
                for i in instructions:
                    if len(i)>0:
                        ax.append( i.split(':')[0].replace(" ", "")  )
                        ax_instructions.append( i.split(':')[1] )
        
                ax_instructions_ = []
                for i in ax_instructions:
                    ax_instructions_.append( [j for j in i.split() if len(j)>0] )
                    
                print(ax_instructions_)
                for long_run in range(self.Nruns):
                    scan_dictionary["RUN"+str(long_run+1)] = {}
                    index = 0
                    for eje in ax:
                        if len(eje.split("_"))>1:
                            eje, parallel_axes = eje.split("_") 
                        else: parallel_axes = ''
                        print("\nROUND ", str(long_run+1)+"/"+str(self.Nruns), " AX", eje)
                        
                        if not check_if_in_dictionary(scan_dictionary, "RUN"+str(long_run+1), eje): scan_dictionary["RUN"+str(long_run+1)][eje] = {};
                        
                        for motion in ax_instructions_[index]:
                            motion_ = motion.split("/");
                            if len(motion_) == 1:
                                motion_ = motion_[0]
                                initial, final, go_back = self.initial_final(motion_)
                                repetition = 1
                            else:
                                repetition = int(motion_[-1])
                                motion_ = motion_[0]
                                initial, final, go_back = self.initial_final(motion_)
                            print("\nInitial t =", '{0:.5f}'.format(initial), " Final t =", '{0:.5f}'.format(final), "(ps)    go_back", go_back) 
                            initial *= self.fac*self.C*1e-9/2;  final *= self.fac*self.C*1e-9/2;  
                            print("Initial d =", '{0:.5f}'.format(initial), " Final d =", '{0:.5f}'.format(final), " (mm)") 
                            send_discord("SCAN: "+str(long_run+1)+"/"+str(self.Nruns)+"\nDELAY: "+str(motion_)) 

                            if not check_if_in_dictionary(scan_dictionary, "RUN"+str(long_run+1), eje, motion):  scan_dictionary["RUN"+str(long_run+1)][eje][motion] = {};
                            
                            if len(eje) == 1:
                                for rep_run in range(repetition):
                                    dataset_index = rep_run+1
                                    
                                    print("\r*** "+str(rep_run+1)+"/"+str(repetition), end="")
                                    Xvalues = []; Yvalues = []; Y2values = [];
                                    if check_if_in_dictionary(scan_dictionary, "RUN"+str(long_run+1), eje,  motion, "DATA"+str(dataset_index)):
                                        dataset_index = int(list(scan_dictionary["RUN"+str(long_run+1)][eje][motion].keys())[-1][4:])+1
                                        scan_dictionary["RUN"+str(long_run+1)][eje][motion]["DATA"+str(dataset_index)] = {}
                                    else:
                                        scan_dictionary["RUN"+str(long_run+1)][eje][motion]["DATA"+str(dataset_index)] = {}
                                    
                                    while_distance = initial; position_scan = self.AXP0[int(eje)-1] - self.AXOFF[int(eje)-1]  + initial;  position_scan = np.round(position_scan,6)
                                    steps_to_run = int(np.ceil( np.abs(final-initial)/STEPSIZEmm ))
                                    
                                    # Move to initial position/delay.
                                    for pa in parallel_axes:
                                        STAGE_AXES[int(pa)-1].set_position( self.AXP0[int(pa)-1] +  initial, updatePlot = False, sleep=1, XY = this_measureXY )
                                    STAGE_AXES[int(eje)-1].set_position( position_scan, updatePlot = True, sleep=1, XY = this_measureXY )
                                    
                                    if final-initial>0:
                                        motion_index = 0;
                                        while motion_index <= steps_to_run: # while_distance<final:
                                            #startSTEP = time.time() ### ERASE
                                            if self.STOPscan: self.RUN.setEnabled(True); return
                                            sleep = 0.02 if motion_index>=3 else 0.15 if motion_index == 0 else 0.06
                                            position_scan += STEPSIZEmm; STAGE_AXES[int(eje)-1].set_position( position_scan, sleep=sleep, XY = this_measureXY ); # while_distance += STEPSIZEmm;
                                            motion_index += 1; 
                                            #endSTEP = time.time(); print("\n", (endSTEP - startSTEP)*1000) ### ERASE
                                            if motion_index%15 == 0: time.sleep(1.0);  # STAGE_AXES[int(eje)-1].start_relative_motion( STEPSIZEmm, sleep=0.35 )
                                    else:
                                        motion_index = 0;
                                        while motion_index <= steps_to_run: # while_distance>final:
                                            #startSTEP = time.time() ### ERASE
                                            if self.STOPscan: self.RUN.setEnabled(True); return
                                            sleep = 0.02 if motion_index>=3 else 0.15 if motion_index == 0 else 0.06 # sleep = 0.01 if motion_index>=3 else 0.1 if motion_index == 0 else 0.05
                                            position_scan -= STEPSIZEmm; STAGE_AXES[int(eje)-1].set_position( position_scan, sleep=sleep, XY = this_measureXY ); # while_distance -= STEPSIZEmm;  # STAGE_AXES[int(eje)-1].start_relative_motion( -STEPSIZEmm, sleep=0.35 )
                                            motion_index += 1; 
                                            #endSTEP = time.time(); print("\n", (endSTEP - startSTEP)*1000) ### ERASE
                                            if motion_index%10 == 0: time.sleep(1.0); 
                                            
                                    if go_back:
                                        while_distance = initial
                                        if final-initial>0:
                                            while while_distance<final: while_distance += STEPSIZEmm; STAGE_AXES[int(eje)-1].start_relative_motion( -STEPSIZEmm, sleep=0.4 )
                                        else:
                                            while while_distance>final: while_distance -= STEPSIZEmm; STAGE_AXES[int(eje)-1].start_relative_motion( STEPSIZEmm, sleep=0.4 )                              
    
                                    scan_dictionary["RUN"+str(long_run+1)][eje][motion]["DATA"+str(dataset_index)]["X"] = Xvalues
                                    scan_dictionary["RUN"+str(long_run+1)][eje][motion]["DATA"+str(dataset_index)]["Y1"] = Yvalues
    
                                    if NinstrLOCKIN > 1: scan_dictionary["RUN"+str(long_run+1)][eje][motion]["DATA"+str(dataset_index)]["Y2"] = Y2values
                                    
                                    if  self.file_extension == 'json':
                                        with open(file_to_save, 'w') as fp: json.dump(scan_dictionary, fp)
                                    else:
                                        now = datetime.now(); 
                                        if NinstrLOCKIN == 1:
                                            scan_dictionary["RUN"+str(long_run+1)][eje][motion_]["DATA"+str(dataset_index)]["Y1"] = Yvalues
                                            np.savetxt(dir_name + 'SCAN' + str(long_run+1) + '_' + eje + '_' + motion_.replace("<", "l").replace(">", "r") + '_' + now.strftime("%m-%d-%Y-%H-%M") + '.txt', np.c_[Xvalues, Yvalues])
                                        else:
                                            scan_dictionary["RUN"+str(long_run+1)][eje][motion_]["DATA"+str(dataset_index)]["Y1"] = Yvalues
                                            scan_dictionary["RUN"+str(long_run+1)][eje][motion_]["DATA"+str(dataset_index)]["Y2"] = Y2values
                                            np.savetxt(dir_name + 'SCAN' + str(long_run+1) + '_' + eje + '_' + motion_.replace("<", "l").replace(">", "r") + '_' + now.strftime("%m-%d-%Y-%H-%M") + '.txt', np.c_[Xvalues, Yvalues, Y2values])                                    
                                    time.sleep(1)
                                    STAGE_AXES[int(eje)-1].set_position( self.AXP0[int(eje)-1] , updatePlot = False,  sleep=3, XY = this_measureXY )
                            else:
                                for rep_run in range(repetition):
                                    if self.STOPscan: self.RUN.setEnabled(True); return
                                    print("\r*** "+str(rep_run+1)+"/"+str(repetition), end="")
                                    Xvalues = []; Yvalues = []; Y2values = [];
                                    
                                    # Move to initial position/delay.
                                    for pa in parallel_axes:
                                        STAGE_AXES[int(pa)-1].set_position( self.AXP0[int(pa)-1] +  initial, updatePlot = False, sleep=3, XY = this_measureXY )       
                                    STAGE_AXES[0].set_group_position( eje, np.array(self.AXP0) - np.array(self.AXOFF) + initial, updatePlot = True, sleep=3  )

                                    while_distance = initial;
                                    if final-initial>0:
                                        while while_distance<final: while_distance += STEPSIZEmm; STAGE_AXES[0].start_group_relative_motion( eje, STEPSIZEmm, sleep=0.4 )
                                    else:
                                        while while_distance>final: while_distance -= STEPSIZEmm; STAGE_AXES[0].start_group_relative_motion( eje, -STEPSIZEmm, sleep=0.4 )
                                    if go_back:
                                        while_distance = initial
                                        if final-initial>0:
                                            while while_distance<final: while_distance += STEPSIZEmm; STAGE_AXES[0].start_group_relative_motion( eje, -STEPSIZEmm, sleep=0.4 )
                                        else:
                                            while while_distance>final: while_distance -= STEPSIZEmm; STAGE_AXES[0].start_group_relative_motion( eje, STEPSIZEmm, sleep=0.4 )
                                    scan_dictionary["RUN"+str(long_run+1)][eje][motion]["DATA"+str(dataset_index)]["X"] = Xvalues
                                    scan_dictionary["RUN"+str(long_run+1)][eje][motion]["DATA"+str(dataset_index)]["Y1"] = Yvalues
                                    if NinstrLOCKIN > 1: scan_dictionary["RUN"+str(long_run+1)][eje][motion]["DATA"+str(dataset_index)]["Y2"] = Y2values
                                    if  self.file_extension == 'json':
                                        with open(file_to_save, 'w') as fp: json.dump(scan_dictionary, fp)
                                    else:
                                        now = datetime.now(); 
                                        if NinstrLOCKIN == 1:
                                            scan_dictionary["RUN"+str(long_run+1)][eje][motion_]["DATA"+str(dataset_index)]["Y1"] = Yvalues
                                            np.savetxt(dir_name + 'SCAN' + str(long_run+1) + '_' + eje + '_' + motion_.replace("<", "l").replace(">", "r") + '_' + now.strftime("%m-%d-%Y-%H-%M") + '.txt', np.c_[Xvalues, Yvalues])
                                        else:
                                            scan_dictionary["RUN"+str(long_run+1)][eje][motion_]["DATA"+str(dataset_index)]["Y1"] = Yvalues
                                            scan_dictionary["RUN"+str(long_run+1)][eje][motion_]["DATA"+str(dataset_index)]["Y2"] = Y2values
                                            np.savetxt(dir_name + 'SCAN' + str(long_run+1) + '_' + eje + '_' + motion_.replace("<", "l").replace(">", "r") + '_' + now.strftime("%m-%d-%Y-%H-%M") + '.txt', np.c_[Xvalues, Yvalues, Y2values])                                    
                                    if not go_back: STAGE_AXES[0].start_group_relative_motion( eje, (initial-final)*self.fac*STEPSIZEmm, updatePlot = False )
                        index += 1
                
                
                self.RUN.setEnabled(True); 
                self.parent.pushButton.setEnabled(True);
                self.parent.pushButton2.setEnabled(True);
                self.P0current.setEnabled(True);
                self.AX1pos.setEnabled(True); self.AX2pos.setEnabled(True); self.AX3pos.setEnabled(True);
                self.AX1offset.setEnabled(True);  self.AX2offset.setEnabled(True);  self.AX3offset.setEnabled(True);
                
                
                end_time = time.time()
                print("\nDONE! ", '{0:.5f}'.format((end_time-start_time)/60), " min")
                send_discord("DONE! " + '{0:.5f}'.format((end_time-start_time)/60) + " min")  
                return
            except Exception as e: print("SCAN ERROR: ", e); send_discord("SCAN ERROR")  
        scan_thread = threading.Thread(target=scan_function, name="scan")
        scan_thread.start()

        
class PLOT_DATA(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plot")
        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        self.layout = QtWidgets.QGridLayout(self._main)
        self.setStyleSheet(  GLOBAL_STYLE  )
        
        self.top = 20
        self.left = 300 
        self.width = 1180 
        self.height = 700
        self.setGeometry(self.top, self.left, self.width, self.height)
        
        self.dictionary = None
        self.long_run = 1
        self.axis = "?"
        self.motion = "?"
        self.small_run = 1
        self.step_size = 1
        self.P0 = [0, 0, 0]
        
        self.dic_LRUN = None
        self.dic_AXES = None
        self.dic_MOTION = None
        self.dic_SRUN  = None
        
        self.layout.addWidget(Demo(1, self), 0, 0, 1, 4)
        
        Dlayout =  QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>RUN</b>") 
        self.LRUN = QSpinBox_(1, 1, 1, self.select_long_run)
        for WIDGET in [Dlabel,  self.LRUN]: Dlayout.addWidget(WIDGET);
        self.layout.addLayout(Dlayout, 1, 0, 1, 1)
  
        Dlayout =  QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Moved Axes</b>") 
        self.AXES = QComboBox_(["?"], 0, self.select_axes)
        for WIDGET in [Dlabel,  self.AXES]: Dlayout.addWidget(WIDGET);
        self.layout.addLayout(Dlayout, 1, 1, 1, 1)

        Dlayout =  QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Motion/Delay</b>") 
        self.MOTION = QComboBox_(["?"], 0, self.select_motion)
        for WIDGET in [Dlabel,  self.MOTION]: Dlayout.addWidget(WIDGET);
        self.layout.addLayout(Dlayout, 1, 2, 1, 1)

        Dlayout =  QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Dataset</b>") 
        self.SRUN = QSpinBox_(1, 1, 1, self.select_small_run)
        for WIDGET in [Dlabel,  self.SRUN]: Dlayout.addWidget(WIDGET);
        self.layout.addLayout(Dlayout, 1, 3, 1, 1)
        
        self.CANVAS = DataCanvas(self)
        self.layout.addWidget(self.CANVAS, 2, 0, 5, 4)
        
        
        Dlayout =  QtWidgets.QHBoxLayout()
        self.Xplot = QComboBox_(["Axis 1", "Axis 2", "Axis 3"], 0, self.set_xarray)
        self.Xunit = QComboBox_(["Distance", "Time", "Steps", "Frequency"], 0, self.set_xunit)
        for WIDGET in [ self.Xplot,  self.Xunit]: Dlayout.addWidget(WIDGET);
        self.layout.addLayout(Dlayout, 7, 0, 1, 4)
        
        self.Daverage = QtWidgets.QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>Average</b>") 
        self.toggleAverage = AnimatedToggle(checked_color="#00AA80", pulse_checked_color="#44FFB000")
        self.toggleAverage.clicked.connect(self.turn_average); self.toggleAverage.setChecked(False)
        for WIDGET in [Dlabel, self.toggleAverage]: self.Daverage.addWidget(WIDGET)
        Dlabel =  QLabel_(my_style+"<b>Averaging Mode</b>") 
        self.AVmode = QComboBox_(["RMS Averaging", "Vector Averaging", "Peak Hold"], 0, self.set_averaging_mode)
        for WIDGET in [Dlabel, self.AVmode]: self.Daverage.addWidget(WIDGET)
        Dlabel =  QLabel_(my_style+"<b>Weighting Mode</b>") 
        self.WTmode = QComboBox_(["Linear", "Exponential"], 0, self.set_weighting_mode)
        for WIDGET in [Dlabel, self.WTmode]: self.Daverage.addWidget(WIDGET)
        Dlabel =  QLabel_(my_style+"<b>Averages</b>")
        self.NAVR_ = QSpinBox_(1, 19999, 1, self.set_number_averages)
        for WIDGET in [Dlabel,  self.NAVR_]: self.Daverage.addWidget(WIDGET);
        self.layout.addLayout(self.Daverage, 8, 0, 1, 4)

        #self.layout.setColumnStretch(0, 2); self.layout.setColumnStretch(1, 2);  self.layout.setColumnStretch(2, 2);
        self.layout.setRowStretch(0, 1); self.layout.setRowStretch(1, 1)
        self.layout.setRowStretch(2, 5); self.layout.setRowStretch(7, 1)

        
        self.setLayout(self.layout)
        
    def turn_average(self, value):
        self.CANVAS.average = True if value else False
        self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.axis,  self.motion, "DATA"+str(self.small_run)   ], self.dictionary)
    def set_averaging_mode(self, value):
        self.CANVAS.averaging_mode = value
        self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.axis,  self.motion, "DATA"+str(self.small_run)   ], self.dictionary)
    def set_weighting_mode(self, value):
        self.CANVAS.weighting_mode = value
        self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.axis,  self.motion, "DATA"+str(self.small_run)   ], self.dictionary)
    def set_number_averages(self, value):
        self.CANVAS.number_averages = value
        self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.axis,  self.motion, "DATA"+str(self.small_run)   ], self.dictionary)

    def select_long_run(self, value):
        def df():
            self.long_run  = value;
            self.dic_AXES = list(self.dictionary["RUN"+str(self.long_run)].keys())
            self.AXES.blockSignals(True); self.AXES.clear(); self.AXES.addItems(self.dic_AXES); self.axis = self.dic_AXES[0]; self.AXES.blockSignals(False)
            self.dic_MOTION = list(self.dictionary["RUN"+str(self.long_run)][self.axis].keys())
            self.MOTION.blockSignals(True); self.MOTION.clear(); self.MOTION.addItems(self.dic_MOTION); self.motion = self.dic_MOTION[0]; self.MOTION.blockSignals(False)
            self.dic_SRUN = list(self.dictionary["RUN"+str(self.long_run)][self.axis][self.motion].keys())
            self.SRUN.blockSignals(True); self.SRUN.setMaximum(len(self.dic_SRUN)); self.small_run = 1; self.SRUN.blockSignals(False)
            self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.dic_AXES[0], self.dic_MOTION[0], self.dic_SRUN[0]   ], self.dictionary)
        df_thread = threading.Thread(target=df, name="df")
        df_thread.start()
    def select_axes(self, value):  
        def df():
            self.axis =  self.dic_AXES[value]; 
            self.dic_MOTION = list(self.dictionary["RUN"+str(self.long_run)][self.axis].keys())
            self.MOTION.blockSignals(True); self.MOTION.clear(); self.MOTION.addItems(self.dic_MOTION); self.motion = self.dic_MOTION[0]; self.MOTION.blockSignals(False)
            self.dic_SRUN = list(self.dictionary["RUN"+str(self.long_run)][self.axis][self.motion].keys())
            self.SRUN.blockSignals(True); self.SRUN.setMaximum(len(self.dic_SRUN)); self.small_run = 1; self.SRUN.blockSignals(False)
            self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.axis, self.dic_MOTION[0], self.dic_SRUN[0]   ], self.dictionary)
        df_thread = threading.Thread(target=df, name="df")
        df_thread.start()
    def select_motion(self, value): 
        def df():
            self.motion = self.dic_MOTION[value];
            self.dic_SRUN = list(self.dictionary["RUN"+str(self.long_run)][self.axis][self.motion].keys())
            self.SRUN.blockSignals(True); self.SRUN.setMaximum(len(self.dic_SRUN)); self.small_run = 1; self.SRUN.blockSignals(False)
            self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.axis,  self.motion, self.dic_SRUN[0]   ], self.dictionary)
        df_thread = threading.Thread(target=df, name="df")
        df_thread.start()
    def select_small_run(self, value): 
        def df():
            self.small_run = value;
            self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.axis,  self.motion, "DATA"+str(self.small_run)   ], self.dictionary)
        df_thread = threading.Thread(target=df, name="df")
        df_thread.start()
        
    def set_xarray(self, value): 
        def df():
            self.CANVAS.to_plot = value; 
            self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.axis,  self.motion, "DATA"+str(self.small_run) ], self.dictionary)
        df_thread = threading.Thread(target=df, name="df")
        df_thread.start()
    def set_xunit(self, value):
        def df():
            self.CANVAS.distance_time = value; 
            self.CANVAS._update_canvas_([ "RUN"+str(self.long_run), self.axis,  self.motion, "DATA"+str(self.small_run) ], self.dictionary)
        df_thread = threading.Thread(target=df, name="df")
        df_thread.start()
    def update(self):
        def df():
            self.CANVAS.dictionary = self.dictionary
            self.CANVAS.step_size = self.dictionary["Step Size"]; 
            self.CANVAS.P0 = [ self.dictionary["AX1 center"], self.dictionary["AX2 center"], self.dictionary["AX3 center"]  ]
            try: self.CANVAS.fac = self.dictionary["+-1"]; self.dic_LRUN = list(self.dictionary.keys())[5:]
            except: self.dic_LRUN = list(self.dictionary.keys())[4:]
            #self.dic_LRUN = list(self.dictionary.keys())[5:]
            self.LRUN.blockSignals(True); self.LRUN.setMaximum(len(self.dic_LRUN)); self.long_run = 1; self.LRUN.blockSignals(False)
            self.dic_AXES = list(self.dictionary["RUN1"].keys())
            self.AXES.blockSignals(True); self.AXES.clear(); self.AXES.addItems(self.dic_AXES); self.axis = self.dic_AXES[0]; self.AXES.blockSignals(False)
            self.dic_MOTION = list(self.dictionary["RUN1"][self.axis].keys())
            self.MOTION.blockSignals(True); self.MOTION.clear(); self.MOTION.addItems(self.dic_MOTION); self.motion = self.dic_MOTION[0]; self.MOTION.blockSignals(False)
            self.dic_SRUN = list(self.dictionary["RUN1"][self.axis][self.motion].keys())
            self.SRUN.blockSignals(True); self.SRUN.setMaximum(len(self.dic_SRUN)); self.small_run = 1; self.SRUN.blockSignals(False)
            self.CANVAS._update_canvas_([ self.dic_LRUN[0], self.dic_AXES[0], self.dic_MOTION[0], self.dic_SRUN[0]   ], self.dictionary)
        df_thread = threading.Thread(target=df, name="df")
        df_thread.start()

def fourier_periodogram(t, y):
    N = len(t)
    frequency = np.fft.fftfreq(N, t[1] - t[0])
    y_fft = np.fft.fft(y)
    positive = (frequency > 0)
    return frequency[positive], (1. / N) * abs(y_fft[positive]) ** 2

def FFT(data):
    N = len(data)
    return 2/N*abs(np.fft.fft(data))

def exp_average(array):
    Npoints = len(array)
    weights = [ 1/(Npoints-i)**2  for i in range(Npoints)] 
    res = 0
    for weight, point in zip(weights, array):
        res += weight*point
    return res/np.sum(weights)
def average(arrays, type=np.mean, LIMIT=10):
    data_sets = arrays[-LIMIT:]
    Nsets = len(data_sets)
    Npoints = len(data_sets[0])
    return np.array([ type([data_sets[j][i] for j in range(Nsets)]) for i in range(Npoints)])
def RMS_averaged(data, type=np.mean, LIMIT=10):
    N = len(data.T[0])
    FFT_data        = np.fft.fft(data, axis=0)
    FFT_data_real   = 2/N*abs(FFT_data)
    rms_averaged    = np.sqrt(average((FFT_data_real**2).T, type, LIMIT))
    return rms_averaged
def VECTOR_averaged(data, type=np.mean, LIMIT=10):
    N = len(data.T[0])
    FFT_data        = np.fft.fft(data, axis=0)
    real_part_avg   = 2/N*average(np.real(FFT_data).T, type, LIMIT)
    imag_part_avg   = 2/N*average(np.imag(FFT_data).T, type, LIMIT)
    vector_averaged = np.abs(real_part_avg+1j*imag_part_avg)
    return vector_averaged
def PEAK_hold(data, LIMIT=10):
    N = len(data.T[0])
    FFT_data = np.fft.fft(data, axis=0)
    FFT_data_real   = 2/N*abs(FFT_data)
    arrays = FFT_data_real.T
    data_sets = arrays[-LIMIT:]
    Nsets = len(data_sets)
    Npoints = len(data_sets[0])
    return np.array([ max([data_sets[j][i] for j in range(Nsets)]) for i in range(Npoints) ])

def check_error(A):
    try: A; return 1
    except: return 0
    
class DataCanvas(FigureCanvas):
    def __init__(self, parent=None) -> None:
        super().__init__(mpl.figure.Figure())

        self.ax = self.figure.subplots()
        self.ax.set_xlabel('Position [nm]', fontsize=30);
        self.ax.set_ylabel(r"$V_1$ [V]", fontsize=30);
        self.ax.yaxis.label.set_color('red')
        
        if NinstrLOCKIN > 1:
            self.ax2 = self.ax.twinx()
            self.ax2.set_ylabel(r"$V_2$ [V]", fontsize=30);
            self.ax2.yaxis.label.set_color('blue')
            self.ax2.yaxis.get_offset_text().set_fontsize(24)

        self.ax.yaxis.get_offset_text().set_fontsize(24)

        self.to_plot = 0
        self.distance_time = 0;
        self.step_size = 1;
        self.P0 = [0, 0, 0];
        self.C = 299792458
        self.fac = 1
        self.dictionary = None
        self.parent = parent
        
        # AVERAGE
        self.average = False
        self.averaging_mode = 0
        self.weighting_mode = 0
        self.number_averages = 1

        self.ax.tick_params(axis='both', which='major', labelsize=20)
        self.ax.tick_params(axis='both', which='minor', labelsize=20)
        self.ax.patch.set_facecolor('white'); self.ax.patch.set_alpha(0.1)
        self.ax.grid(); 
        
        self.spec0 = None; self.spec1 = None; self.spec2 = None; self.spec3 = None;

        self.line1, = self.ax.plot([], [], 'r');
        self.line1F, = self.ax.plot([], [], 'orange');

        self.line2, = self.ax.plot([], [], 'b');

        self.draw()
        return
    
    def _update_canvas_(self, spec, dictionary):
        try:
            data = dictionary[spec[0]][spec[1]][spec[2]][spec[3]]
            Xdata = data["X"]; Y_ = data["Y1"]
            X =  [i[self.to_plot] for i in Xdata]
            
            if self.average:
                try:
                    SPECTRUM = []; SPECTRUM2 = []
                    motion_to_average = spec[2]
                    ax_to_average = str(self.to_plot+1)
    
                    to_average = [];
                    for i1 in list(dictionary.keys())[5:]:
                        for i2 in list(dictionary[i1].keys()):
                            for i3 in list(dictionary[i1][i2].keys()):
                                for i4 in list(dictionary[i1][i2][i3].keys()):
                                    if ax_to_average in i2 and motion_to_average.split("/")[0] in i3:
                                        try: to_average.append(dictionary[i1][i2][i3][i4])  
                                        except:  pass
                                            
                    SPECTRUM = [i["Y1"] for i in to_average]; new_size = min([ len(i) for i in SPECTRUM ]); 
                    SPECTRUM = np.array([i[0:new_size] for i in SPECTRUM]).T
                    
                    try:  
                        SPECTRUM2 =  [i["Y2"] for i in to_average]
                        new_size = min([ len(i) for i in SPECTRUM2]);
                        SPECTRUM2 = np.array([i[0:new_size] for i in SPECTRUM2]).T
                    except: pass
                except: pass
                
            Xdata = data["X"]; Y_ = data["Y1"]
            X =  [i[self.to_plot] for i in Xdata]
            if   self.distance_time == 0: X_ = X;                                                       self.ax.set_xlabel('Position [nm]', fontsize=30);   self.line1F.set_data([],[]);
            elif self.distance_time == 1: X_ = (np.array(X)-self.P0[self.to_plot])*2e9*self.fac/self.C; self.ax.set_xlabel('Time [ps]', fontsize=30);       self.line1F.set_data([],[]);
            elif self.distance_time == 2: X_ = (np.array(X)-self.P0[self.to_plot])/self.step_size;      self.ax.set_xlabel('Steps', fontsize=30);           self.line1F.set_data([],[]);
            else:
                try:
                    self.ax.set_xlabel('Frequency [THz]', fontsize=30);
                    self.ax.set_ylabel(r"$\tilde{V_1}$ [V$\cdot$s]", fontsize=30);
                    X_ = (np.array(X)-self.P0[self.to_plot])*2e9*self.fac/self.C
                    
                    N = len(X_)
                    T = np.abs(X_[1]-X_[0])
                    X_ = fftfreq(N, T)[0:N//2]
                    
                    if not self.average:
                        Y_ = FFT(Y_)[0:N//2]
                    else:
                        if len(SPECTRUM)==1: Y_ = FFT(SPECTRUM[0])[0:N//2]
                        else:
                            if self.weighting_mode == 0:
                                Y_ = RMS_averaged(SPECTRUM, LIMIT=self.number_averages)[0:N//2] if self.averaging_mode == 0 else VECTOR_averaged(SPECTRUM, LIMIT=self.number_averages)[0:N//2] if self.averaging_mode == 1 else PEAK_hold(SPECTRUM, LIMIT=self.number_averages)[0:N//2]
                            else:
                                Y_ = RMS_averaged(SPECTRUM, type=exp_average, LIMIT=self.number_averages)[0:N//2] if self.averaging_mode == 0 else VECTOR_averaged(SPECTRUM, type=exp_average, LIMIT=self.number_averages)[0:N//2] if self.averaging_mode == 1 else PEAK_hold(SPECTRUM, LIMIT=self.number_averages)[0:N//2]
 
                except Exception  as e: print("Plot ERROR: ", e); pass
                
            self.line1.set_data(X_, Y_);
            self.ax.relim(); self.ax.autoscale_view()
    
            try: 
                Y2_ = data["Y2"]
                if self.distance_time == 3:
                    try:
                           self.ax2.set_ylabel(r"$\tilde{V_2}$ [V$\cdot$s]", fontsize=30);
                           if not self.average:
                               Y2_ = FFT(Y2_)[0:N//2]
                           else:
                               if len(SPECTRUM2)==1: Y2_ = FFT(SPECTRUM2[0])[0:N//2]
                               else:
                                   if self.weighting_mode == 0:
                                       Y2_ = RMS_averaged(SPECTRUM2, LIMIT=self.number_averages)[0:N//2] if self.averaging_mode == 0 else VECTOR_averaged(SPECTRUM2, LIMIT=self.number_averages)[0:N//2] if self.averaging_mode == 1 else PEAK_hold(SPECTRUM2, LIMIT=self.number_averages)[0:N//2]
                                   else:
                                       Y2_ = RMS_averaged(SPECTRUM2, type=exp_average, LIMIT=self.number_averages)[0:N//2] if self.averaging_mode == 0 else VECTOR_averaged(SPECTRUM2, type=exp_average, LIMIT=self.number_averages)[0:N//2] if self.averaging_mode == 1 else PEAK_hold(SPECTRUM2, LIMIT=self.number_averages)[0:N//2]
                    except Exception  as e: print("Plot ERROR: ", e); pass
                self.line2.set_data(X_, Y2_);
                self.ax2.relim(); self.ax2.autoscale_view()
            except:  pass
        
            self.draw()
        except Exception  as e: print("Plot ERROR: ", e); pass
 

class CONEX(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rotation Stage")
        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        self.layout = QtWidgets.QGridLayout(self._main)
        self.setStyleSheet(  GLOBAL_STYLE  )  
        
        
        self.pos = self.get_current_position()
        self.vel = self.get_velocity()
        self.acc = self.get_acceleration()
        self.step_size = 1
        self.STOP = False
        
        self.layout.addWidget(QLabel_(my_style+"<b>"+self.get_controller_revision_information()+"</b>"), 0, 0, 1, 2)
        
        DH = QLabel_(""); DH.setFixedHeight(15)
        self.group_boxPOS = QGroupBox("POSITION"); group_box_layout = QVBoxLayout(); 
        self.POSITION = QLabel_(my_style+"<b>Angle</b> "+str(self.pos)+"\u00B0");
        self.RELmove = QLDoubleSpinBox_(my_style+"<b>Relative motion</b>", -1000, 1000, 0, self.move_relative, "\u00B0", 0.1);
        self.ABSmove = QLDoubleSpinBox_(my_style+"<b>Set angle</b>", -1000, 1000, 0, self.move_absolute, "\u00B0", 0.1);
        self.STEPset = QLDoubleSpinBox_(my_style+"<b>Step size</b>", 0, 1000, self.step_size, self.set_step_size, "\u00B0", 0.1);

        Dlayout1 = QtWidgets.QHBoxLayout()
        self.STP = QPushButton_("  STOP  ", self.STOPmotion); self.STP.setStyleSheet("QPushButton { background:#f08f41; font-weight: bold; }")
        self.toLL = QPushButton_("\u00AB", self.toLeftLeft)
        self.toL = QPushButton_("\u2039", self.toLeft)
        self.toR = QPushButton_("\u203A", self.toRight)
        self.toRR = QPushButton_("\u00BB", self.toRightRight)
        for WIDGET in [self.STP, self.toLL, self.toL, self.toR, self.toRR]: Dlayout1.addWidget(WIDGET);

        self.NEGlimit = QLDoubleSpinBox_(my_style+"<b>Negative limit</b>", -1e12, 0, self.get_negative_limit(), self.set_negative_limit, "\u00B0", 1);
        self.POSlimit = QLDoubleSpinBox_(my_style+"<b>Positive limit</b>", 0, 1e12, self.get_positive_limit(), self.set_positive_limit, "\u00B0", 1);
        for WIDGET in [DH, self.POSITION, self.RELmove, self.ABSmove, self.STEPset, Dlayout1, self.NEGlimit, self.POSlimit ]:  addWidLay(group_box_layout, WIDGET)
        
        group_box_layout.addLayout(Dlayout1)
        self.group_boxPOS.setLayout(group_box_layout)
        self.layout.addWidget(self.group_boxPOS, 1, 0)
        
        DH = QLabel_(""); DH.setFixedHeight(15)
        group_box = QGroupBox("HOME"); group_box_layout = QVBoxLayout()
        self.HOME = QPushButton_("Home Search", self.HOME_search); self.HOME.setStyleSheet("QPushButton { background:#5dff00; font-weight: bold; font-size: 50px;}"); self.HOME.setFixedHeight(110)
        DLab1 = QLabel_(my_style+"<b>Type</b>");
        self.HOMEtype = QComboBox_(['MZ switch and encoder Index', 'Current position as HOME', 'MZ switch only', 'EoR- switch and encoder Index', 'EoR- switch only' ], self.get_HOME_search_type(), self.set_HOME_search_type)
        self.HOMEvelocity = QLDoubleSpinBox_(my_style+"<b>Velocity</b>", 1e-6, 1e12, self.get_HOME_search_velocity(), self.set_HOME_search_velocity, " \u00B0/s", 0.1)
        self.HOMEtimeout = QLDoubleSpinBox_(my_style+"<b>Time-out</b>", 1e-6, 1e12, self.get_HOME_search_velocity(), self.set_HOME_search_velocity, " s", 0.1)
        for WIDGET in [ DH, DLab1, self.HOMEtype, self.HOMEvelocity, self.HOMEtimeout, self.HOME]: addWidLay(group_box_layout, WIDGET)
        group_box.setLayout(group_box_layout)
        self.layout.addWidget(group_box, 1, 1)
        
        DH = QLabel_(""); DH.setFixedHeight(15)
        group_box = QGroupBox("VELOCITY"); group_box_layout = QVBoxLayout()
        self.VELOCITY = QLabel_(my_style+"<b>Current</b> "+str(self.vel)+"\u00B0/s");
        self.VELset = QLDoubleSpinBox_(my_style+"<b>Set</b>", 1e-6, 1e12, self.vel, self.set_velocity, "\u00B0/s", 0.1);
        for WIDGET in [DH, self.VELOCITY, self.VELset]: addWidLay(group_box_layout, WIDGET)
        group_box.setLayout(group_box_layout)
        self.layout.addWidget(group_box, 2, 0)

        DH = QLabel_(""); DH.setFixedHeight(15)
        group_box = QGroupBox("ACCELERATION"); group_box_layout = QVBoxLayout()
        self.ACCELERATION = QLabel_(my_style+"<b>Current</b> "+str(self.acc)+"\u00B0/s\u00B2");
        self.ACCset = QLDoubleSpinBox_(my_style+"<b>Set</b>", 1e-6, 1e12, self.acc, self.set_acceleration, "\u00B0/s\u00B2", 0.1);
        for WIDGET in [DH, self.ACCELERATION, self.ACCset]: addWidLay(group_box_layout, WIDGET)
        group_box.setLayout(group_box_layout)
        self.layout.addWidget(group_box, 2, 1)
        
        self.RESET = QPushButton_("RESET", self.reset_controller); self.RESET.setStyleSheet("QPushButton { background:#9203ff; font-weight: bold; color: white}")
        self.layout.addWidget(self.RESET, 3, 0, 1, 2)


        #group_box_layout.addWidget(QCheckBox("Check Box 1"))
        #group_box_layout.addWidget(QCheckBox("Check Box 2"))
        #group_box_layout.addWidget(QCheckBox("Check Box 3"))

        group_box.setLayout(group_box_layout)
        
        self.setLayout(self.layout)
        
    def instr_action(self, Query, rep=True, ntries=5):
        try:
            instr_rotation.clear();
            instr_rotation.write(Query)
        except:
            time.sleep(0.4); instr_rotation.clear(); time.sleep(0.4); instr_rotation.close();  time.sleep(0.4); instr_rotation.open(); time.sleep(0.4);
            if ntries==0: print("ERROR: ", Query); raise ValueError('INSTRUMENT error.'); return;
            if rep: time.sleep(0.5); self.instr_action(Query, ntries=ntries-1)
    def instr_query(self, Query, sep, rep=True, type=str, ntries=5):
        try:
            instr_rotation.clear();
            to_return = instr_rotation.query(Query)
            return type(to_return.split(sep)[-1])
        except:
            time.sleep(0.4); instr_rotation.clear(); time.sleep(0.4); instr_rotation.close();  time.sleep(0.4); instr_rotation.open(); time.sleep(0.4);
            if ntries==0: print("ERROR: ", Query); raise ValueError('INSTRUMENT error.'); return; 
            if rep: time.sleep(0.5); self.instr_query(Query, sep, type=type, ntries=ntries-1)
        
    def get_current_position(self):
        return self.instr_query('1TP', sep='TP', type=float)
    def move_relative(self, target):
        self.group_boxPOS.setEnabled(False)  
        #time_sleep = self.instr_query('1PT'+str(target), sep='PT', type=float)
        time.sleep(0.3)
        self.instr_action('1PR'+str(target))    
        time.sleep(2*target/15)
        self.group_boxPOS.setEnabled(True)  
        self.update()
    def move_absolute(self, target):
        self.group_boxPOS.setEnabled(False)  
        #time_sleep = self.instr_query('1PT'+str(target-self.pos), sep='PT', type=float)
        time.sleep(0.3)
        self.instr_action('1PA'+str(target))        
        time.sleep(2*np.abs(target-self.pos)/15)
        self.group_boxPOS.setEnabled(True)  
        self.update()
        
    def set_step_size(self, val):
        self.step_size = val
    def STOPmotion(self):
        self.STOP = True; 
        self.instr_action('1ST')
    def toLeftLeft(self):
        self.STOP = False; 
        while not self.STOP:
            self.move_relative(-self.step_size); # time.sleep(0.01); self.update();
            cv2.waitKey(20)
    def toLeft(self): self.move_relative(-self.step_size);
    def toRight(self): self.move_relative(+self.step_size);
    def toRightRight(self):
        self.STOP = False; 
        while not self.STOP:
            self.move_relative(+self.step_size); # time.sleep(0.01); self.update();
            cv2.waitKey(20)
        
    def get_controller_revision_information(self):
        return self.instr_query('1VE', sep='VE')
    def set_negative_limit(self, val):
        if val>-1e12 and val<=0:
            self.instr_action('1SL'+str(val))
    def get_negative_limit(self): 
        return self.instr_query('1SL?', sep='SL', type=float)
    def set_positive_limit(self, val):
        if val<1e12 and val>=0:
            self.instr_action('1SR'+str(val))
    def get_positive_limit(self): 
        return self.instr_query('1SR?', sep='SR', type=float)
    
        
    def HOME_search(self):
        self.instr_action('1OR')   
    def set_HOME_search_type(self, val): # ['MZ switch and encoder Index', 'Current position as HOME', 'MZ switch only', 'EoR- switch and encoder Index', 'EoR- switch only' ]
        self.instr_action('1HT'+str(val))   
    def get_HOME_search_type(self):
        return self.instr_query('1HT?', sep='HT', type=int)
    def set_HOME_search_velocity(self, val):
        if val>1e-6 and val<1e12: self.instr_action('1OH'+str(val))   
    def get_HOME_search_velocity(self):
        return self.instr_query('1OH?', sep='OH', type=float)
    def set_HOME_search_timeout(self, val):
        if val>1 and val<1e3: self.instr_action('1OT'+str(val))   
    def get_HOME_search_timeout(self):
        return self.instr_query('1OT?', sep='OT', type=float)
    
    def set_acceleration(self, val):
        if val>1e-6 and val<1e12: self.instr_action('1AC'+str(val))   
    def get_acceleration(self):
        return self.instr_query('1AC?', sep='AC', type=float)   
    
    def set_velocity(self, val):
        if val>1e-6 and val<1e12: self.instr_action('1VA'+str(val))   
    def get_velocity(self):
        return self.instr_query('1VA?', sep='VA', type=float)   

    def reset_controller(self):
        self.instr_action('1RS')        

        
    def update(self):
        time.sleep(0.1)
        self.pos = self.get_current_position()
        self.POSITION.setText(my_style+"<b>Angle</b> "+str(self.pos)+"\u00B0");
        self.STOPmotion()
     
########## class OSCILLOSCOPE
class OSCILLOSCOPE(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Oscilloscope ")
        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        self.layout = QtWidgets.QGridLayout(self._main)
        self.setStyleSheet(  GLOBAL_STYLE  ) 
        
        self.top = 20
        self.left = 300 
        self.width = 1180 
        self.height = 700
        self.setGeometry(self.top, self.left, self.width, self.height)
        
        self.continue_plot = False
        self.oscilloscope_thread = None
        
        self.start = QPushButton('START')
        self.start.clicked.connect(self.start_oscilloscope)
        self.start.setStyleSheet("QPushButton { background:#06EC3A;  font-weight: bold;}"); 
        
        self.layout.addWidget(self.start, 0, 0)
        
        self.myFig = OSCILLOSCOPECanvas(self)
        self.layout.addWidget(self.myFig, 1, 0)
        
        self.data_display = QLabel_(my_style+"???")
        self.layout.addWidget(self.data_display, 2, 0)
        
        self.layout.setRowStretch(1, 5)
        
        
        self.setLayout(self.layout)
    
    def start_oscilloscope(self):     
        if not self.continue_plot:
            self.continue_plot = True
            self.start.setText('STOP')
            self.oscilloscope_thread = threading.Thread(target=self.myFig._update_canvas_, name="oscilloscope")
            self.oscilloscope_thread.start()
        else:
            self.continue_plot = False
            while self.oscilloscope_thread.is_alive():
                time.sleep(1)
            self.start.setText('START')


class OSCILLOSCOPECanvas(FigureCanvas):
    def __init__(self, parent=None) -> None:
        super().__init__(mpl.figure.Figure()) # facecolor='black'

        self.parent = parent
        self.ax = self.figure.subplots()
        self.ax.set_xlabel('Time $t$ [s]', fontsize=30);
        self.ax.set_ylabel(r"Voltage $V$ [V]", fontsize=30);
        
        self.ax.yaxis.get_offset_text().set_fontsize(24)
        self.ax.xaxis.get_offset_text().set_fontsize(24)

        self.ax.set_facecolor('#0F0F0F')


        self.ax.tick_params(axis='both', which='major', labelsize=20)
        self.ax.tick_params(axis='both', which='minor', labelsize=20)
        self.ax.patch.set_facecolor('white'); self.ax.patch.set_alpha(0.1)
        self.ax.grid(); 
        

        self.line1, = self.ax.plot([], [], 'green', label="A");
        self.line1V,= self.ax.plot([], [], 'green', linestyle='dashed');
        self.line2, = self.ax.plot([], [], 'purple', label="B");
        self.line2V, = self.ax.plot([], [], 'purple', linestyle='dashed');
        self.lines = [self.line1, self.line2]
        self.linesV = [self.line1V, self.line2V]
        
        
        self.ax.legend(prop=dict(size=30), loc='upper center', bbox_to_anchor=(0.5, 1.15),
          fancybox=True, shadow=True, ncol=2)


        self.draw()
        return
    
    def _update_canvas_(self):
        while self.parent.continue_plot:
            try:            
                list1 = []
                list2 = []
                for i in ['1','2']: # '3','4'
                    try:
                        Xmult = float(instr_OSCILLOSCOPE.query('WFMPre:'+'CH'+i+':XINcr?'))
                        Xoff  = float(instr_OSCILLOSCOPE.query('WFMPre:'+'CH'+i+':PT_Off?'))
                        Xzero = float(instr_OSCILLOSCOPE.query('WFMPre:'+'CH'+i+':XZEro?'))
                        
                        Ymult = float(instr_OSCILLOSCOPE.query('WFMPre:'+'CH'+i+':YMUlt?'))
                        Yoff  = float(instr_OSCILLOSCOPE.query('WFMPre:'+'CH'+i+':YOFf?'))
                        Yzero = float(instr_OSCILLOSCOPE.query('WFMPre:'+'CH'+i+':YZEro?'))
    
                        instr_OSCILLOSCOPE.write('CURVe?')
                        time.sleep(0.8)
                        
                        dataY = [(float(j)-Yoff)*Ymult+Yzero for j in instr_OSCILLOSCOPE.read().split(',')]
                        dataX = [(j-Xoff)*Xmult+Xzero for j in range(len(dataY))]
                        max_index = dataY.index(max(dataY))
                        # plt.axvline(x = dataX[max_index], color = colors[int(i)-1], linestyle='dashed')
                        self.linesV[int(i)-1].set_data([dataX[max_index], dataX[max_index]], [min(dataY), max(dataY)])
                        self.lines[int(i)-1].set_data(dataX, dataY)
                        list1.append(dataX[max_index]);
                        list2.append(dataY[max_index]);
                    except: pass
                
                dx1 = units.convert(list1[0])
                dx2 = units.convert(list2[0])
                dx3 = units.convert(list1[1])
                dx4 = units.convert(list2[1])
                dx5 = units.convert(list1[0]-list1[1])
                dx6 = units.convert(list2[0]-list2[1])
                self.parent.data_display.setText( my_style + "<b>&Delta;(A-B):</b> &nbsp; &nbsp; &nbsp;  &Delta;<i>t</i> = " + str(np.round(dx5[0],3)) + " " + dx5[1] + "s  &nbsp; &nbsp; &nbsp;    &Delta;<i>V</i> = " + str(np.round(dx6[0],3)) + " " + dx6[1] + "V<br><b>max<sub>A</sub>:</b> &nbsp; &nbsp; &nbsp;  <i>t</i> = " + str(np.round(dx1[0],3)) + " " + dx1[1] + "s   &nbsp; &nbsp; &nbsp;   <i>V</i> = " + str(np.round(dx2[0],3)) + " " + dx2[1] + "V<br><b>max<sub>B</sub>:</b> &nbsp; &nbsp; &nbsp;  <i>t</i> = " + str(np.round(dx3[0],3)) + " " + dx3[1] + "s  &nbsp; &nbsp; &nbsp;    <i>V</i> = " + str(np.round(dx4[0],3)) + " " + dx4[1] + "V" )
                self.ax.relim(); self.ax.autoscale_view()
                self.draw()
                time.sleep(0.1)
            except Exception  as e: print("Plot ERROR: ", e); pass                
     
########## class HEATER       
class HEATER(QMainWindow):
    def __init__(self, channel):
        
        super().__init__()
        self.setWindowTitle("Heater")
        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        self.layout = QtWidgets.QGridLayout(self._main)
        self.setStyleSheet(  GLOBAL_STYLE  ) 
        self.channel = str(channel)
        
        
        # DH = QLabel_(""); DH.setFixedHeight(15)
        
        PID =  self.getPID()
        self.groupPID = QGroupBox("PID"); group_box_layout = QVBoxLayout(); 
        self.P = QLDoubleSpinBox_(my_style+"<b>P</b>", 0, 1000, PID[0], self.setPID, "", 0.1);
        self.I = QLDoubleSpinBox_(my_style+"<b>I</b>", 1, 1000, PID[1], self.setPID, "", 0.1);
        self.D = QLDoubleSpinBox_(my_style+"<b>D</b>", 1, 200, PID[2], self.setPID, "", 1);
        for WIDGET in [self.P, self.I, self.D ]:  addWidLay(group_box_layout, WIDGET)
        self.groupPID.setLayout(group_box_layout)
        self.layout.addWidget(self.groupPID, 0, 0)
        
        RAMP =  self.getRAMP()
        self.groupRAMP = QGroupBox("RAMP"); group_box_layout = QVBoxLayout(); 
        self.RAMP = QLDoubleSpinBox_(my_style+"<b>Ramp</b>", 0, 100, RAMP[1], self.setRAMP, " K/min", 0.1);
        Dlayout =  QHBoxLayout()
        Dlabel =  QLabel_(my_style+"<b>ON/OFF</b>"); Dlabel.setFixedWidth(100)
        self.RAMP01 = AnimatedToggle(checked_color="#00AA80", pulse_checked_color="#44FFB000")
        self.RAMP01.clicked.connect(self.setRAMP)
        if RAMP[0] == 1: self.RAMP01.setChecked(True)
        else: self.RAMP01.setChecked(False)
        Dlayout.addWidget(Dlabel); Dlayout.addWidget(self.RAMP01 ); 
        for WIDGET in [self.RAMP, Dlayout]:  addWidLay(group_box_layout, WIDGET)
        self.groupRAMP.setLayout(group_box_layout)
        self.layout.addWidget(self.groupRAMP, 0, 1)
        
        self.warming = False
        self.groupHEAT = QGroupBox("HEATER"); group_box_layout = QVBoxLayout(); 
        self.SETPOINT = QLDoubleSpinBox_(my_style+"<b>Setpoint</b>", 0, 1000, self.getSETPOINT(), self.setSETPOINT, "", 0.1);
        Dlabel =  QLabel_(my_style+"<b>Range</b>");
        self.RANGE = QComboBox_(["Off", "Low", "Medium", "High"], self.getRANGE(), self.setRANGE);
        self.HEAT = QProgressBar(); self.getHEAT()
        for WIDGET in [self.SETPOINT, self.RANGE, self.HEAT ]:  addWidLay(group_box_layout, WIDGET)
        self.groupHEAT.setLayout(group_box_layout)
        self.layout.addWidget(self.groupHEAT, 1, 0)
             
        self.setLayout(self.layout)
        
        
    def my_query(self, to_send):
        for j in range(5):
            try:
                instrumentHEATER = Model336()
                res = instrumentHEATER.query(to_send)
                instrumentHEATER.disconnect_usb()
                return res
                break
            except Exception as e: 
                try: instrumentHEATER.disconnect_usb()
                except: pass
                print("HEATER error: ", e); time.sleep(2)
        return 0
    def my_command(self, to_send):
        for j in range(5):
            try:
                instrumentHEATER = Model336()
                instrumentHEATER.command(to_send)
                instrumentHEATER.disconnect_usb()
                break
            except Exception as e: 
                try: instrumentHEATER.disconnect_usb()
                except: pass
                print("HEATER error: ", e); time.sleep(2)
        return 0                
        
    def getPID(self): 
        PID = (self.my_query('PID? '+self.channel)).split(",")
        return float(PID[0]), float(PID[1]), float(PID[2])
    def setPID(self, value): 
        for i in [self.P, self.I, self.D]: i.setEnabled(False)
        self.my_command('PID '+self.channel+','+str(self.P.itemAt(1).widget().value())+','+str(self.I.itemAt(1).widget().value())+','+str(self.D.itemAt(1).widget().value()))
        for i in [self.P, self.I, self.D]: i.setEnabled(True)
    def getRAMP(self):
        RAMP = self.my_query('RAMP? '+self.channel).split(",")
        return int(RAMP[0]), float(RAMP[1])
    def setRAMP(self, value):
        for i in [self.RAMP, self.RAMP01]: i.setEnabled(False)
        self.my_command('RAMP '+self.channel+','+str(int(self.RAMP01.isChecked()))+','+str(self.RAMP.itemAt(1).widget().value()) )
        for i in [self.RAMP, self.RAMP01]: i.setEnabled(True)
    def getRANGE(self):
        return int(self.my_query('RANGE? '+self.channel))
    def setRANGE(self, value):
        for i in [self.RANGE]: i.setEnabled(False)
        self.my_command('RANGE '+self.channel+','+str(value) )
        for i in [self.RANGE]: i.setEnabled(True)
    def getSETPOINT(self):
        return float(self.my_query('SETP? '+self.channel))
    def setSETPOINT(self, value):
        for i in [self.SETPOINT]: i.setEnabled(False)
        self.my_command('SETP '+self.channel+','+str(value) )
        for i in [self.SETPOINT]: i.setEnabled(True)
    def getHEAT(self):
        res =  float(self.my_query(('HTR? '+self.channel)))
        self.HEAT.setValue(int(res))

  
file_name = ''                    
dir_name = ''                
class FileBrowser(QWidget):
    OpenFile = 0
    OpenFiles = 1
    OpenDirectory = 2
    SaveFile = 3
    def __init__(self, index, title, mode=OpenFile, parent=None):
        QWidget.__init__(self)
        layout = QHBoxLayout()
        self.index = index
        self.setLayout(layout)
        self.browser_mode = mode
        self.filter_name = 'Text files (*.json)' # "Text files (*.txt)" 'All files (*.*)'
        self.dirpath = QDir.currentPath()
        self.parent = parent
        
        self.label = QLabel()
        self.label.setText(title)
        self.label.setText("<p style=\"font-family:\'Times New Roman\';font-size:25px;\"> <b>"+ title +"</b> </p>")
        
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.label)
        
        self.lineEdit = QLineEdit(self)
        
        layout.addWidget(self.lineEdit)
        
        self.button = QPushButton('Search')
        self.button.clicked.connect(self.getFile)
        layout.addWidget(self.button)
        layout.addStretch()

    def setMode(self, mode):
        self.mode = mode
    def setFileFilter(self, text):
        self.filter_name = text        
    def setDefaultDir(self, path):
        self.dirpath = path
    def getFile(self):
        global file_name, dir_name;
        self.filepaths = []
        
        if self.browser_mode == FileBrowser.OpenFile:
            self.filepaths.append(QFileDialog.getOpenFileName(self, caption='Choose File',
                                                    directory=self.dirpath,
                                                    filter=self.filter_name)[0]) 
            if self.index == 1: 
                file_name = self.filepaths[0]; 
                try:
                    with open(file_name) as json_file:
                        try: self.parent.dictionary = json.load(json_file); self.parent.update(); 
                        except: pass;
                except: pass

        elif self.browser_mode == FileBrowser.OpenFiles:
            self.filepaths.extend(QFileDialog.getOpenFileNames(self, caption='Choose Files',
                                                    directory=self.dirpath,
                                                    filter=self.filter_name)[0])
        elif self.browser_mode == FileBrowser.OpenDirectory:
            self.filepaths.append(QFileDialog.getExistingDirectory(self, caption='Choose Directory',
                                                    directory=self.dirpath))
            if self.index == 0: dir_name = self.filepaths[0] + '/'
        else:
            options = QFileDialog.Options()
            if sys.platform == 'darwin':
                options |= QFileDialog.DontUseNativeDialog
            self.filepaths.append(QFileDialog.getSaveFileName(self, caption='Save/Save As',
                                                    directory=self.dirpath,
                                                    filter=self.filter_name,
                                                    options=options)[0])
        if len(self.filepaths) == 0:
            return
        elif len(self.filepaths) == 1:
            self.lineEdit.setText(self.filepaths[0])
        else:
            self.lineEdit.setText(",".join(self.filepaths))    
    def setLabelWidth(self, width):
        self.label.setFixedWidth(width)    
    def setlineEditWidth(self, width):
        self.lineEdit.setFixedWidth(width)
    def getPaths(self):
        return self.filepaths

class Demo(QDialog):
    def __init__(self, index:int, parent=None):
        QDialog.__init__(self, parent)
        
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.setWindowTitle("File Browsing Dialog")
        self.index = index
        self.parent = parent
        
        vlayout = QVBoxLayout()
        self.setLayout(vlayout)    
        
        self.fileBrowserPanel(vlayout)
        vlayout.addStretch()
        self.show()
    def fileBrowserPanel(self, parentLayout):
        if self.index == 0:
            vlayout = QVBoxLayout()
            self.dirFB = FileBrowser(0, 'Dir ', FileBrowser.OpenDirectory)
            vlayout.addWidget(self.dirFB)
            vlayout.addStretch()
            parentLayout.addLayout(vlayout)
        elif self.index == 1:
            vlayout = QVBoxLayout()
            self.fileFB = FileBrowser(1, 'Open File', FileBrowser.OpenFile, self.parent)
            vlayout.addWidget(self.fileFB)
            vlayout.addStretch()
            parentLayout.addLayout(vlayout)
        else:
            vlayout = QVBoxLayout()
            self.fileFB = FileBrowser(2, 'Archive 2', FileBrowser.OpenFile)
            vlayout.addWidget(self.fileFB)
            vlayout.addStretch()
            parentLayout.addLayout(vlayout)
            
    def addButtonPanel(self, parentLayout):
        hlayout = QHBoxLayout()
        hlayout.addStretch()
        
        self.button = QPushButton("OK")
        self.button.clicked.connect(self.buttonAction)
        hlayout.addWidget(self.button)
        parentLayout.addLayout(hlayout)
    
    def buttonAction(self):
        print(self.fileFB.getPaths())
        print(self.dirFB.getPaths())
                    

STAGE_AXES = [None, None, None]    
mySCAN = None    
myLOCKINs = []
myCONEX = None
myOSCILLOSCOPE = None
class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        global STAGE_AXES, mySCAN, myLOCKINs, myCONEX
        
        self.title = "Pulse"
        self.top = 90
        self.left = 90
        self.width = 880
        self.height = 700
        
        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        self.layout = QtWidgets.QGridLayout(self._main)

        self.setStyleSheet(  GLOBAL_STYLE  )
        
        try: self.setWindowIcon(QtGui.QIcon('Laser.png'))
        except: pass
        
        self.myFig = MyFigureCanvas()
        #plot_thread = threading.Thread(target=self.myFig.background_update, name="background_update")
        #plot_thread.start()
        
        plot_thread2 = threading.Thread(target=self.myFig._update_canvas_, name="plot_update")
        plot_thread2.start()
        
        # LOCK-IN
        myLOCKINs = [LOCKIN(0)]
        self.LOCKIN = myLOCKINs[0]
        if NinstrLOCKIN > 1: myLOCKINs.append(LOCKIN(1)); self.LOCKIN2 = myLOCKINs[1]
        # STAGE AXES
        self.STAGE1 = STAGE(0, 1, self.myFig)
        self.STAGE2 = STAGE(0, 2, self.myFig)
        self.STAGE3 = STAGE(0, 3, self.myFig)
        STAGE_AXES = [ self.STAGE1, self.STAGE2, self.STAGE3 ]
        # SCAN
        mySCAN = SCAN(self)
        self.SCAN = mySCAN
        # PLOT DATA
        self.PLOTdata = PLOT_DATA()
        # ROTATION STAGE
        try:
            myCONEX = CONEX()
            self.CONEX = myCONEX
            self.pushCONEX = QPushButton("ROTATION", self); self.pushCONEX.setStyleSheet("QPushButton { background:#0DBDB2;  font-weight: bold;}"); 
            self.pushCONEX.setToolTip("<h3>Open rotation stage</h3>")
            self.pushCONEX.clicked.connect(self.window2(self.CONEX)) 
        except Exception as e: print(e);  pass
    
        try:
            myOSCILLOSCOPE = OSCILLOSCOPE()
            self.OSCILLOSCOPE = myOSCILLOSCOPE
            self.pushOSCILLOSCOPE = QPushButton("OSCILLOSCOPE", self); self.pushOSCILLOSCOPE.setStyleSheet("QPushButton { background:#CA33FF;  font-weight: bold;}"); 
            self.pushOSCILLOSCOPE.setToolTip("<h3>Open oscilloscope</h3>")
            self.pushOSCILLOSCOPE.clicked.connect(self.window2(self.OSCILLOSCOPE)) 
        except Exception as e: print(e);  pass

        self.pushButton = QPushButton("LOCK-IN", self); self.pushButton.setStyleSheet("QPushButton { background:#A8E10C;  font-weight: bold;}"); #self.pushButton.move(275, 200)
        self.pushButton.setToolTip("<h3>Open lock-in amplifier</h3>")
        self.pushButton.clicked.connect(self.window2(self.LOCKIN))

        self.pushButton2 = QPushButton("STAGE", self); self.pushButton2.setStyleSheet("QPushButton { background:#8A6FDF; font-weight: bold; }");  #self.pushButton2.move(475, 200)
        self.pushButton2.setToolTip("<h3>Open motion controller</h3>")
        self.pushButton2.clicked.connect(self.window2(self.STAGE1))      
        
        self.pushButton3 = QPushButton("SCAN", self); self.pushButton3.setStyleSheet("QPushButton { background:#FFBD15;  font-weight: bold;}"); 
        self.pushButton3.setToolTip("<h3>Open scan controls</h3>")
        self.pushButton3.clicked.connect(self.window2(self.SCAN)) 
        
        
        self.pushButton4 = QPushButton("PLOT", self); self.pushButton4.setStyleSheet("QPushButton { background:#FF5765; font-weight: bold; }"); 
        self.pushButton4.setToolTip("<h3>Plot data</h3>")
        self.pushButton4.clicked.connect(self.window2(self.PLOTdata)) 
        
        
        Dlayout = QHBoxLayout(); Dlayout.addWidget( self.pushButton );  Dlayout.addWidget( self.pushButton2 );   Dlayout.addWidget( self.pushButton3 );          Dlayout.addWidget( self.pushButton4 ); 

        
        Dlayout1 = QHBoxLayout();
        try: Dlayout1.addWidget( self.pushCONEX );
        except: pass
        try: Dlayout1.addWidget( self.pushOSCILLOSCOPE );
        except: pass
    
        self.HEATER = HEATER(2)
        self.pushHEATER = QPushButton("HEATER", self); self.pushHEATER.setStyleSheet("QPushButton { background:#FF5733; font-weight: bold; }"); 
        self.pushHEATER.setToolTip("<h3>Heater</h3>")
        self.pushHEATER.clicked.connect(self.window2(self.HEATER))
        Dlayout1.addWidget( self.pushHEATER );
    
        self.layout.addLayout(Dlayout, 0, 0, 1, 1)
        self.layout.addLayout(Dlayout1, 1, 0, 1, 1)

        Dlayout = QVBoxLayout(); Dlayout.addWidget(self.myFig)
        self.layout.addLayout(Dlayout, 2, 0, 5, 1)
        
        Dlayout = QHBoxLayout(); 
        self.RESETcanvas = QPushButton("RESET", self); self.RESETcanvas.setStyleSheet("QPushButton { background:#000000; color: white; }");
        self.RESETcanvas.setToolTip("<h3>Reset plot</h3>")
        self.RESETcanvas.clicked.connect(self.reset_canvas)
        
        self.Xplot = QComboBox_(["Axis 1", "Axis 2", "Axis 3"], 0, self.set_xarray)
        self.Xunit = QComboBox_(["Distance", "Time"], 0, self.set_xunit)
        for WIDGET in [self.RESETcanvas, self.Xplot, self.Xunit]: Dlayout.addWidget(WIDGET)
        self.layout.addLayout(Dlayout, 7, 0, 1, 1)

        Dlayout = QHBoxLayout()

        self.main_window()
        
    def reset_canvas(self):
        global Xvalues, Yvalues, Y2values;
        Xvalues = [[STAGE_AXES[0].var1, STAGE_AXES[0].var2, STAGE_AXES[0].var3]]; Yvalues = [Ylast]; Y2values = [Y2last];
    
    def set_xarray(self, value): self.myFig.to_plot = value 
    def set_xunit(self, value): self.myFig.distance_time = value 

    def closeEvent(self, event):
       global continue_background, continue_plot
       reply = QMessageBox.question(
            self, "Message",
            "Are you sure you want to quit? Any unsaved work will be lost.",
            QMessageBox.Close | QMessageBox.Cancel)
       if reply == QMessageBox.Close:
            continue_background = False; continue_plot = False
            instrSTAGE[0].clear(); instrSTAGE[0].close(); 
            instrLOCKIN[0].clear(); instrLOCKIN[0].close(); 
            instr_rotation.clear(); instr_rotation.close();
            for i in STAGE_AXES: i.hide()
            for i in myLOCKINs: i.hide()
            try: myCONEX.hide()
            except: pass
            try: myOSCILLOSCOPE.hide()
            except: pass
            mySCAN.hide()
            self.PLOTdata.hide()
            event.accept()
       else:
            event.ignore()

    def main_window(self):
        #self.label = QLabel("Manager", self)
        #self.label.move(285, 175)
        self.setWindowTitle(self.title)
        self.setGeometry(self.top, self.left, self.width, self.height)
        self.show()

    def window2(self, MYWINDOW):
        def W2():                                    
            self.w = MYWINDOW
            self.w.show()
        return W2
        


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    sys.exit(app.exec())