# Heartware 

### About the Project

Heartware is a pacemaker – a safety critical implant – which regulates a user’s heart rate by sending electrical pulses to the heart’s nodes. Such devices are used to treat conditions such as arrhythmia and bradycardia, where a patient’s heart is unable to sufficiently regulate its own rate. 

Please read the documentation for more details.

The current version of Heartware utilizes model-based code generation and a Python GUI to achieve the following features:
- 4 unique pacemaker modes (AOO, VOO, AAI, VVI)
- Desktop application for a DCM (Device Control Monitor)

## Software Requirements
[Python](https://www.python.org/) | [Matlab Simulink](https://www.mathworks.com/products/simulink.html) | [PyQt](https://doc.qt.io/qtforpython-5/index.html#) | [NXP FRDM K64F Board](https://www.nxp.com/design/design-center/development-boards/freedom-development-boards/mcu-boards/freedom-development-platform-for-kinetis-k64-k63-and-k24-mcus:FRDM-K64F) | [J-Link](https://www.segger.com/downloads/jlink/)

## Gallery

## Installation
#### Dependencies
1. Python 3.11.5. or later
2. MATLAB Simulink 2020a

#### Python Libraries
Install the libraries with the following lines:
```commandline
pip install pyqt5
```
and
```commandline
pip install hashlib
```

#### MATLAB Libraries
- Simulink, Embedded Coder, Fixed-Point Designer, MATLAB Coder, Simulink Check, Simulink Coder, Simulink Coverage, Simulink Design Verifier, Simulink Desktop Real-Time, Simulink Test, and Stateflow
- Simulink Coder Support Package for NXP FRDM-K64F Board
- Kinetis SDK v1.2.0 Mainline
- V6.20a of the J-Link Software and Documentation pack

Enter the following command in the MATLAB Command window (copy and paste exactly):
```matlab
open([codertarget.freedomk64f.internal.getSpPkgRootDir, '/src/mw_sdk_interface.c']);
```
In the file that opens, replace the following line:
```matlab
{ GPIO_MAKE_PIN(GPIOA_IDX, 0), MW_NOT_USED}, //PTA0, D8
```
with:
```matlab
{ GPIO_MAKE_PIN(GPIOC_IDX, 12), MW_NOT_USED}, //PTC12, D8
```

## Contributors
[Zainab Iqbal](https://www.linkedin.com/in/zainab-iqbal-9909161b7/) |
[Maryam Khatib](https://www.linkedin.com/in/maryam-khatib-7a7732283/) |
[Min Yi Liu](https://www.linkedin.com/in/min-yi-liu/) |
[Alex Sun](https://www.linkedin.com/in/alex-sun-89a76b223/) |
[Cynthia Sun](https://www.linkedin.com/in/cynthiayuansun/) |
[Karolina Teresinska](https://www.linkedin.com/in/karolina-teresinska-22a042293/)

