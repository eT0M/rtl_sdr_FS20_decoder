Decoding FS20 home automation protocoll data with RTL-SDR and GNU Radio
========================================================================

Thomas Frisch
email: dev@e-tom.de

Since i have some FS20 based components in use and under development, 
there was a need for an universal decoder for the FS20 protocol. Normaly i had done 
this as a stand alone µC solutiuon, but my intention was to dig deeper into the RTL-SDR stuff.

The concept of the OOK decoder and accessing GNU Radio samples live from Python is based in the remote thermometer script
posted by Kevin Mehall. 
https://github.com/kevinmehall/rtlsdr-433m-sensor

This script decodes the packets used within a FS20 home automation system which uses the 868MHz SDR
band for wireless communication. 
Typical FS20 components are:
- wireless phase control dimmer
- Switches
- remote controls
- wireless door bells
- alarm system

Features of the decoder:
- Live print out of:
  - Housecode
  - Adresses / Subadresses
  - Command with resolution of the meaning
  - Extension Byte
  - Parity and checksum checksum
  

Each packet is send multiple times by the transmitter (usually 2 or 3 times). The modulation is
OOK with the following symbols:
logical 1: pulse of 600µs
logical 0: pulse of 400µs

Details on the protocoll can be found here:
http://fhz4linux.info/tiki-index.php?page=FS20%20Protocol

