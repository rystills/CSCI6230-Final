#my job is to store networking globals, as well as common used across modules
import socket

inConn = outConn = None
outSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
securingConnection = False
BUFFER_SIZE = 4096
inPort = outPort = None
#TODO: set ip and port in GUI
inIp = socket.gethostbyname(socket.gethostname())
outIp = '127.0.0.1'
gui = None
pubKey = None
privKey = None
macKey = None

kDistPrefList = [] #preference for establishing a secure connection (distributing keys)
encPrefList = [] #preference for message encryption/decryption
kDistPref = None
encPref = None 