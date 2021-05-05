#!/usr/bin/env python3
# This MCP3008 adc is multi channel.  If any channel has a delta (current-previous) that is above the
# noise threshold then the voltage from all channels will be returned.
# MQTT version has a publish section in the main code to test MQTT ability stand alone
import sys, json, logging, re
import RPi.GPIO as GPIO
from time import sleep
import paho.mqtt.client as mqtt
from os import path
from pathlib import Path
from logging.handlers import RotatingFileHandler
import rotaryencoder
from debugging import Timer

class pcolor:
    ''' Add color to print statements '''
    LBLUE = '\33[36m'   # Close to CYAN
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    DBLUE = '\33[34m'
    WOLB = '\33[46m'    # White On LightBlue
    LPURPLE = '\033[95m'
    PURPLE = '\33[35m'
    WOP = '\33[45m'     # White On Purple
    GREEN = '\033[92m'
    DGREEN = '\33[32m'
    WOG = '\33[42m'     # White On Green
    YELLOW = '\033[93m'
    YELLOW2 = '\33[33m'
    RED = '\033[91m'
    DRED = '\33[31m'
    WOR = '\33[41m'     # White On Red
    BOW = '\33[7m'      # Black On White
    BOLD = '\033[1m'
    ENDC = '\033[0m'

class CustomFormatter(logging.Formatter):
    """ Custom logging format with color """

    grey = "\x1b[38;21m"
    green = "\x1b[32m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "[%(levelname)s]: %(name)s - %(message)s"

    FORMATS = {
        logging.DEBUG: green + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

def setup_logging(log_dir, logger_type, logger_name=__name__, log_level=logging.INFO, mode=1):
    ''' Create basic or custom loggers with RotatingFileHandler '''
    global _loggers
    # logger_type = basic
    # logger_type = custom with log file options below
                # log_level and mode will determine output
                    #log_level, RFHmode|  logger.x() | output
                    #------------------|-------------|-----------
                    #      INFO, 1     |  info       | print
                    #      INFO, 2     |  info       | print+logfile
                    #      INFO, 3     |  info       | logfile
                    #      DEBUG,1     |  info+debug | print only
                    #      DEBUG,2     |  info+debug | print+logfile
                    #      DEBUG,3     |  info+debug | logfile

    if logger_type == 'basic':
        if len(logging.getLogger().handlers) == 0:       # Root logger does not already exist, will create it
            logging.basicConfig(level=log_level) # Create Root logger
            custom_logger = logging.getLogger(logger_name)    # Set logger to root logging
        else:
            custom_logger = logging.getLogger(logger_name)   # Root logger already exists so just linking logger to it
    else:
        if mode == 1:
            logfile_log_level = logging.CRITICAL
            console_log_level = log_level
        elif mode == 2:
            logfile_log_level = log_level
            console_log_level = log_level
        elif mode == 3:
            logfile_log_level = log_level
            console_log_level = logging.CRITICAL

        custom_logger = logging.getLogger(logger_name)
        custom_logger.propagate = False
        custom_logger.setLevel(log_level)
        log_file_format = logging.Formatter("[%(levelname)s] - %(asctime)s - %(name)s - : %(message)s in %(pathname)s:%(lineno)d")
        #log_console_format = logging.Formatter("[%(levelname)s]: %(message)s") # Using CustomFormatter Class

        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_log_level)
        console_handler.setFormatter(CustomFormatter())

        log_file_handler = RotatingFileHandler('{}/debug.log'.format(log_dir), maxBytes=10**6, backupCount=5) # 1MB file
        log_file_handler.setLevel(logfile_log_level)
        log_file_handler.setFormatter(log_file_format)

        log_errors_file_handler = RotatingFileHandler('{}/error.log'.format(log_dir), maxBytes=10**6, backupCount=5)
        log_errors_file_handler.setLevel(logging.WARNING)
        log_errors_file_handler.setFormatter(log_file_format)

        custom_logger.addHandler(console_handler)
        custom_logger.addHandler(log_file_handler)
        custom_logger.addHandler(log_errors_file_handler)
    if custom_logger not in _loggers: _loggers.append(custom_logger)
    return custom_logger
                
def on_connect(client, userdata, flags, rc):
    """ on connect callback verifies a connection established and subscribe to TOPICs"""
    main_logger.info("attempting on_connect")
    if rc==0:
        mqtt_client.connected = True
        for topic in MQTT_SUB_TOPIC:
            client.subscribe(topic)
            main_logger.info("Subscribed to: {0}\n".format(topic))
        main_logger.info("Successful Connection: {0}".format(str(rc)))
    else:
        mqtt_client.failed_connection = True  # If rc != 0 then failed to connect. Set flag to stop mqtt loop
        main_logger.info("Unsuccessful Connection - Code {0}".format(str(rc)))

def on_message(client, userdata, msg):
    """on message callback will receive messages from the server/broker. Must be subscribed to the topic in on_connect"""
    mqtt_logger.debug("Received: {0} with payload: {1}".format(msg.topic, str(msg.payload)))

def on_publish(client, userdata, mid):
    """on publish will send data to client"""
    mqtt_logger.debug("msg ID: " + str(mid)) 
    pass 

def on_disconnect(client, userdata,rc=0):
    main_logger.info("DisConnected result code "+str(rc))
    mqtt_client.loop_stop()

def mqtt_setup(IPaddress):
    global MQTT_SERVER, MQTT_CLIENT_ID, MQTT_USER, MQTT_PASSWORD, MQTT_SUB_TOPIC, MQTT_PUB_LVL1, MQTT_SUB_LVL1, MQTT_REGEX
    global mqtt_client
    home = str(Path.home())                       # Import mqtt and wifi info. Remove if hard coding in python script
    with open(path.join(home, "stem"),"r") as f:
        user_info = f.read().splitlines()
    MQTT_SERVER = IPaddress                    # Replace with IP address of device running mqtt server/broker
    MQTT_USER = user_info[0]                   # Replace with your mqtt user ID
    MQTT_PASSWORD = user_info[1]               # Replace with your mqtt password

    # Specific MQTT SUBSCRIBE/PUBLISH TOPICS created inside 'setup_device' function
    MQTT_SUB_TOPIC = []
    MQTT_SUB_LVL1 = 'nred2' + MQTT_CLIENT_ID
    MQTT_PUB_LVL1 = 'pi2nred/'

def setup_device(device, lvl2, publvl3, data_keys):
    global printcolor, deviceD
    if deviceD.get(device) == None:
        deviceD[device] = {}
        deviceD[device]['data'] = {}
        deviceD[device]['lvl2'] = lvl2 # Sub/Pub lvl2 in topics. Does not have to be unique, can piggy-back on another device lvl2
        topic = f"{MQTT_SUB_LVL1}/{deviceD[device]['lvl2']}ZCMD/+"
        if topic not in MQTT_SUB_TOPIC:
            MQTT_SUB_TOPIC.append(topic)
            for key in data_keys:
                deviceD[device]['data'][key] = 0
        else:
            for key in data_keys:
                for item in deviceD:
                    if deviceD[item]['data'].get(key) != None:
                        main_logger.warning(f"**DUPLICATE WARNING {device} and {item} are both publishing {key} on {topic}")
                deviceD[device]['data'][key] = 0
        deviceD[device]['pubtopic'] = MQTT_PUB_LVL1 + lvl2 + '/' + publvl3
        deviceD[device]['send'] = False
        printcolor = not printcolor # change color of every other print statement
        if printcolor: 
            main_logger.info(f"{pcolor.LBLUE}{device} Subscribing to: {topic}{pcolor.ENDC}")
            main_logger.info(f"{pcolor.DBLUE}{device} Publishing  to: {deviceD[device]['pubtopic']}{pcolor.ENDC}")
            main_logger.info(f"JSON payload keys will be:{pcolor.WOLB}{*deviceD[device]['data'],}{pcolor.ENDC}")
        else:
            main_logger.info(f"{pcolor.PURPLE}{device} Subscribing to: {topic}{pcolor.ENDC}")
            main_logger.info(f"{pcolor.LPURPLE}{device} Publishing  to: {deviceD[device]['pubtopic']}{pcolor.ENDC}")
            main_logger.info(f"JSON payload keys will be:{pcolor.WOP}{*deviceD[device]['data'],}{pcolor.ENDC}")
    else:
        main_logger.error(f"Device {device} already in use. Device name should be unique")
        sys.exit(f"{pcolor.RED}Device {device} already in use. Device name should be unique{pcolor.ENDC}")

def main():
    global deviceD, printcolor             # Containers setup in 'create' functions and used for Publishing mqtt
    global MQTT_SERVER, MQTT_USER, MQTT_PASSWORD, MQTT_CLIENT_ID, mqtt_client, MQTT_PUB_LVL1
    global _loggers, main_logger, mqtt_logger

    main_logger_level= logging.DEBUG # CRITICAL=logging off. DEBUG=get variables. INFO=status messages.
    main_logger_type = 'custom'       # 'basic' or 'custom' (with option for log files)
    RFHmode = 1 # log level and RFH mode will determine output for custom loggers
                #log_level, mode   |  logger.x() | output
                #------------------|-------------|-----------
                #      INFO, 1     |  info       | print
                #      INFO, 2     |  info       | print+logfile
                #      INFO, 3     |  info       | logfile
                #      DEBUG,1     |  info+debug | print only
                #      DEBUG,2     |  info+debug | print+logfile
                #      DEBUG,3     |  info+debug | logfile

    _loggers = [] # container to keep track of loggers created
    main_logger = setup_logging(path.dirname(path.abspath(__file__)), main_logger_type, log_level=main_logger_level, mode=RFHmode)
    mqtt_logger = setup_logging(path.dirname(path.abspath(__file__)), 'custom', 'mqtt', log_level=logging.INFO, mode=1)
    
    # MQTT structure: lvl1 = from-to     (ie Pi-2-NodeRed shortened to pi2nred)
    #                 lvl2 = device type (ie servoZCMD, stepperZCMD, adc)
    #                 lvl3 = free form   (ie controls, servo IDs, etc)
    MQTT_CLIENT_ID = 'pi' # Can make ID unique if multiple Pi's could be running similar devices (ie servos, ADC's) 
                          # Node red will need to be linked to unique MQTT_CLIENT_ID
    mqtt_setup('10.0.0.115') # IP address

    printcolor = True
    deviceD = {}  # Primary container for storing all devices, topics, and data
    
    #==== HARDWARE SETUP =====#
    rotaryEncoderSet = {}
    rotenc_logger = setup_logging(path.dirname(path.abspath(__file__)), 'custom', 'rotenc', log_level=logging.DEBUG, mode=2)

    device = "rotEnc1"  # Device name should be unique, can not duplicate device ID
    lvl2 = 'rotencoder' # Topic lvl2 name can be a duplicate, meaning multiple devices publishing data on the same topic
    publvl3 = MQTT_CLIENT_ID + "" # Will be a tag in influxdb. Optional to modify it and describe experiment being ran
    data_keys = ['RotEnc1Ci', 'RotEnc1Bi'] # If topic lvl2 name repeats would likely want the data_keys to be unique
    clkPin, dtPin, button_rotenc = 17, 27, 24
    setup_device(device, lvl2, publvl3, data_keys)
    rotaryEncoderSet[device] = rotaryencoder.RotaryEncoder(clkPin, dtPin, button_rotenc, *data_keys, rotenc_logger)
    
    # For example - uncomment to see error/sys.exit due to duplicate devices
    #device = "rotEnc2"
    #lvl2 = 'rotencoder'
    #publvl3 = MQTT_CLIENT_ID + "Test2" # Will be a tag in influxdb. Optional to modify it and describe experiment being ran
    #data_keys = ['RotEnc2Ci', 'RotEnc2Bi']
    #clkPin, dtPin, button_rotenc = 18, 26, 25
    #setup_device(device, lvl2, data_keys)
    #rotaryEncoderSet[device] = rotaryencoder.RotaryEncoder(clkPin, dtPin, button_rotenc, *data_keys, rotenc_logger)

    print("\n")
    for logger in _loggers:
        main_logger.info('{0} is set at level: {1}'.format(logger, logger.getEffectiveLevel()))

    #==== START/BIND MQTT FUNCTIONS ====#
    # Create a couple flags to handle a failed attempt at connecting. If user/password is wrong we want to stop the loop.
    mqtt.Client.connected = False          # Flag for initial connection (different than mqtt.Client.is_connected)
    mqtt.Client.failed_connection = False  # Flag for failed initial connection
    # Create our mqtt_client object and bind/link to our callback functions
    mqtt_client = mqtt.Client(MQTT_CLIENT_ID) # Create mqtt_client object
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD) # Need user/password to connect to broker
    mqtt_client.on_connect = on_connect    # Bind on connect
    mqtt_client.on_disconnect = on_disconnect             # Bind on disconnect
    mqtt_client.on_message = on_message    # Bind on message
    mqtt_client.on_publish = on_publish    # Bind on publish
    main_logger.info("Connecting to: {0}".format(MQTT_SERVER))
    mqtt_client.connect(MQTT_SERVER, 1883) # Connect to mqtt broker. This is a blocking function. Script will stop while connecting.
    mqtt_client.loop_start()               # Start monitoring loop as asynchronous. Starts a new thread and will process incoming/outgoing messages.
    # Monitor if we're in process of connecting or if the connection failed
    while not mqtt_client.connected and not mqtt_client.failed_connection:
        main_logger.info("Waiting")
        sleep(1)
    if mqtt_client.failed_connection:
        mqtt_client.loop_stop()
        sys.exit(f"{pcolor.RED}Connection failed. Use rc code to trouble shoot{pcolor.ENDC}")

    #==== MAIN LOOP ====================#
    try:
        while True:
            for device, rotenc in rotaryEncoderSet.items():
                deviceD[device]['data'] = rotenc.runencoder()
                if deviceD[device]['data'] is not None:
                    mqtt_client.publish(deviceD[device]['pubtopic'], json.dumps(deviceD[device]['data']))
    except KeyboardInterrupt:
        main_logger.info(f"{pcolor.YELLOW}Exit with ctrl-C{pcolor.ENDC}")
    finally:
        GPIO.cleanup()
        main_logger.info(f"{pcolor.CYAN}GPIO cleaned up{pcolor.ENDC}")

if __name__ == "__main__":
    # Run main loop            
    main()