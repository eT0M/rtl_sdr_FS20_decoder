#!/usr/bin/env python
"""
Decoder for ELV FS20 home automation protocol
using RTL-SDR and GNU Radio
Frequ.: 868.35 MHz
(C) 2013 Th. Frisch
Licensed under the terms of the GNU GPLv3+

NOTE: The data aquisition part and OOK decoder is originally from Kevin Mehall
"""

from gnuradio import gr
import gr_queue
from gnuradio import blks2
from gnuradio import audio
from gnuradio.gr import firdes
import osmosdr


freq = 868.23e6
freq_offs = 120e3   #Offset to avoid noise at 0Hz downconversion

# Threshold for OOK
level = -0.35

class rtlsdr_am_stream(gr.top_block):
    """ A GNU Radio top block that demodulates AM from RTLSDR and acts as a 
    python iterator for AM audio samples.
        
    Optionally plays the audio out the speaker.
    """

    def __init__(self, center_freq, offset_freq, decimate_am=1):
        """Configure the RTL-SDR and GNU Radio"""
        super(rtlsdr_am_stream, self).__init__()
        
        audio_rate = 48000
        device_rate = audio_rate * 25
        output_rate = audio_rate / float(decimate_am)
        self.rate = output_rate
        
        self.osmosdr_source = osmosdr.source_c("")
        self.osmosdr_source.set_sample_rate(device_rate)
        self.osmosdr_source.set_center_freq(freq)
              
        self.osmosdr_source.set_freq_corr(0, 0)
        self.osmosdr_source.set_gain_mode(1, 0)
        self.osmosdr_source.set_gain(20, 0)
                     
        taps = firdes.low_pass(1, device_rate, 40000, 5000, firdes.WIN_HAMMING, 6.76)
        self.freq_filter = gr.freq_xlating_fir_filter_ccc(25, taps, -freq_offs, device_rate)
    
        self.am_demod = blks2.am_demod_cf(
            channel_rate=audio_rate,
            audio_decim=1,
            audio_pass=5000,
            audio_stop=5500,
        )
        
        self.resampler = blks2.rational_resampler_fff(
            interpolation=1,
            decimation=decimate_am,
        )
        
        self.sink = gr_queue.queue_sink_f()
    
        self.connect(self.osmosdr_source, self.freq_filter, self.am_demod)
        self.connect(self.am_demod, self.resampler, self.sink)
    
    
    def __iter__(self):
        return self.sink.__iter__()

def transition(data, level=-0.35):
	"""Threshold a stream and yield transitions and their associated timing.
	Used to detect the On-Off-Keying (OOK)"""
	last_state = False
	last_i = 0
	for i, y_sample in enumerate(data):
		state = (y_sample > level)
		if state != last_state:
			yield (state, i-last_i, i)
			last_i = i
			last_state = state

def decode_osv1(stream, level=-0.35):
    """Decoder waits for a rising edge after 5ms lowlime and decodes pulse-width"""
    
    state = 'wait'
    pkt = []
    for direction, time, abstime in transition(stream, level):
        # convert the time in samples to microseconds
        time = time / float(stream.rate) * 1e6
        if state == 'wait' and direction is True and time > 5000:
             # Wait for Rising edge after l5ms low phase
            state = 'data'
            pkt = []
            framelength = 58
        elif state == 'data':
            # Receive Data Block
            if direction is True:
                # Rising edge (end of LOW level)
                if (290 < time < 800):
                     pass   #positive condition for debug reasons
                else:
                     state = 'wait'
                    	
            else:
                # Falling edge (end of HIGH level)
                if (290 < time <= 510):
                    pkt.append(0)
                elif (510 < time < 800):
                    pkt.append(1)
                else:
                    #print "invalid high time", time
                    state = 'wait'
            if (len(pkt) == 13) and ((sum(pkt) != 1) or (pkt[12] != 1)):	
                    #print "corrupt preamble"
                    state = 'wait'
                                
            #Look at bit 42 while reception to determine the target length (set extension bit means 67 bit total length, otherwise 58)
            if   len(pkt)==43 and pkt[42] == 1:
                framelength = 67
            
            #Detect end of frame
            if len(pkt) >= framelength:
                # Packet complete. 
                # print "Packet complete, %i Bit received" %len(pkt)
                # print pkt     #Debug
                yield Packet(pkt)
                state = 'wait'


class Packet(object):		
    def __init__(self, recdata):
         """ Parse received packet into FS20 fields. """
         self.recdata = recdata
         self.length = len(recdata)
         #Housecode 1
         self.hc1 = (self.recdata[13]*2 + self.recdata[14] +1) * 1000 + (self.recdata[15]*2 + self.recdata[16] +1) * 100 + (self.recdata[17]*2 + self.recdata[18] +1) * 10 + (self.recdata[19]*2 + self.recdata[20] +1) 
         #Housecode 1 parity check
         self.hc1_p = (sum(self.recdata[13:21])%2 ==  self.recdata[21])         
         #Housecode 2
         self.hc2 = (self.recdata[22]*2 + self.recdata[23] +1) * 1000 + (self.recdata[24]*2 + self.recdata[25] +1) * 100 + (self.recdata[26]*2 + self.recdata[27] +1) * 10 + (self.recdata[28]*2 + self.recdata[29] +1) 
         #Housecode 2 parity check
         self.hc2_p = (sum(self.recdata[22:30])%2 ==  self.recdata[30])
         #Adressgroup
         self.ag =   (self.recdata[31]*2 + self.recdata[32] +1) * 10 + (self.recdata[33]*2 + self.recdata[34] +1)  
         #Subadressgroup
         self.sg =   (self.recdata[35]*2 + self.recdata[36] +1) * 10 + (self.recdata[37]*2 + self.recdata[38] +1)  
         #Adressgroup parity check
         self.asg_p = (sum(self.recdata[31:39])%2 ==  self.recdata[39])    
         #Command
         self.cmd = self.bits2num(43, 5, 2)
         #Extension
         self.ext = self.recdata[42]
         #Bidirectional
         self.bidi = self.recdata[41]
         #Answer
         self.answer = self.recdata[40]
         #Command parity check
         self.cmd_p = (sum(self.recdata[40:48])%2 ==  self.recdata[48])    
         
         #Apply offset in case of extension bit is set
         if self.ext == 1 and len(self.recdata) == 67 and self.cmd_p is True:
             ext_offset = 9
             self.extension =  self.bits2num(49, 8, 2)
         else:
             ext_offset = 0 
             self.extension = 0
       
         #Checksum
         self.checksum = self.recdata[ext_offset+49]*128 + self.recdata[ext_offset+50]*64 + self.recdata[ext_offset+51]*32+ self.recdata[ext_offset+52]*16 +self.recdata[ext_offset+53]*8 +self.recdata[ext_offset+54]*4 +self.recdata[ext_offset+55]*2+self.recdata[ext_offset+56]
         #Calculate Checksum 
         self.calc_checksum =  self.bits2num(13, 8, 2)+self.bits2num(22, 8, 2)+self.bits2num(31, 8, 2)+self.bits2num(40, 8, 2) + 6
         
         if self.ext == 1:
             #self.calc_checksum +=  self.recdata[49]*128 + self.recdata[50]*64 + self.recdata[51]*32+ self.recdata[52]*16 +self.recdata[53]*8 +self.recdata[54]*4 +self.recdata[55]*2+self.recdata[56]+6
             self.calc_checksum +=  self.bits2num(49, 8, 2) + 6
              
         while self.calc_checksum > 255:
             self.calc_checksum = self.calc_checksum - 256      
      
         #Check Checksum
         self.check =  (self.checksum == self.calc_checksum)            
     
    def bits2num(self, pos,  length, base):
        sum = 0
        i = 0
        while i < length:
            sum *= base
            sum += self.recdata[pos+i]
            i+=1
        return sum
		
if __name__ == '__main__':
    import sys
    import time
    
    # Command description resolution
    cmdres = {00 : '"off"',
    1 : '"on" with 6.25%', \
    2 : '"on" with 12.5%', \
    3 : '"on" with 18.75%', \
    4 : '"on" with 25%', \
    5 : '"on" with 31.25%', \
    6 : '"on" with 37.5%', \
    7 : '"on" with 43.75%' , \
    8 : '"on" with 50%', \
    9 : '"on" with 56.25%' , \
    10 : '"on" with 62.5%' , \
    11 : '"on" with 68.75%' , \
    12 : '"on" with 75%' , \
    13 : '"on" with 81.25%' , \
    14 : '"on" with 87.5%' ,\
    15 : '"on" with 93.75%' , \
    16 : '"on" with 100%' ,\
    17 : '"on" with last value', \
    18 : 'toggle between on - off - last_value' , \
    19 : 'dim up', \
    20 : 'dim down', \
    21 : 'dim in a loop up-pause-down-pause', \
    22 : 'set timer (start, end)', \
    23 : 'status request (only for bidirectional devices)', \
    24 : 'off, timer', \
    25 : 'on, timer', \
    26 : 'last value, timer', \
    27 : 'reset to default', \
    29 : 'not used', \
    30 : 'not used', \
    31 : 'not used'}

    
    stream = rtlsdr_am_stream(freq, freq_offs, decimate_am=2)
    stream.start()
    print"Decoder for FS20 home automation protocol \nusing RTL-SDR and GNU Radio\nFrequ.: 868.35 MHz\n(C) 2013 Th. Frisch\n"
    packet_nbr=1;
    for packet in decode_osv1(stream):
        
        if packet.cmd_p is True  and packet.hc1_p is True and   packet.hc2_p is True and packet.asg_p is True and packet.check is True:
            result =  '\033[1;32mPacket OK\033[1;m'
        else:
            result =  '\033[1;31mParity/Checksum error\033[1;m'
                                        
        
        print "-- FS20 Packet - No. %i --------- Packet Length: %i bit ---------- %s --------------" %(packet_nbr,  packet.length,  result)
        packet_nbr+=1
        print "Housecode: %s-%s "%(packet.hc1,  packet.hc2) 
        print "Housecode Parity ok (code1/code2): %s/%s" %(packet.hc1_p,  packet.hc2_p)
        print "Adressgroup/Subadressgroup: %i-%i " %(packet.ag,  packet.sg)
        print "Adress Parity ok: %s" %(packet.asg_p)
        print "Command: %i, %s" %(packet.cmd,  cmdres[packet.cmd])
        print "Message extenstion Bit: %s" % packet.ext
        print "Bidirectional Bit: %s" % packet.bidi
        print "Answer from receiver Bit: %s" % packet.answer
        print "Command Parity ok: %s " % packet.cmd_p
        if packet.ext == 1:
             print "Extension Byte: %i" % packet.extension
        print "Checksum: %i " % packet.checksum
        print "Checksum ok: %s\n" % packet.check
        
     
