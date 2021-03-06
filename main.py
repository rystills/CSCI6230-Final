import socket
import threading
import time
import sys
import random
import cryptoutil
import json; encoder = json.JSONEncoder(); decoder = json.JSONDecoder()
from DES import DES
from NS_DH import NS_DH
from BG import BG
from Paillier import Paillier
from AES import AES
from RSA import rsa
import GUI
import networking as net
import hashing

"""
send a message on whichever connection is currently open
@param msg: the string message (not yet utf-8 encoded) to send
"""
def sendMessage(msg,shouldEncrypt=True):
    print("sending {0}".format(msg))
    if (net.inConn):
        print("sending on net.inConn")
        net.inConn.send((encryptMsg(msg) if shouldEncrypt else msg).encode("utf-8"))
    elif (net.outConn):
        print("sending on net.outConn")
        net.outConn.send((encryptMsg(msg) if shouldEncrypt else msg).encode("utf-8"))

"""
encrypt a msg using the current selected encryption algorithm
@param msg: the message to encrypt
@returns the encrypted message
"""
def encryptMsg(msg):
    if (net.encPref == "DES"):
        encrypted = cryptoutil.frombits(DES.encrypt(cryptoutil.tobits(msg),DES.defaultKey))
    elif (net.encPref == "BG"):
        bits,x = BG.BGPEnc(cryptoutil.tobits(msg),net.privKey.l,net.privKey.m)
        #encrypt a JSON encoded tuple of (c,x) where c is the stringified encrypted bit list and x is the t+1th iteration of the random seed exponentiation
        encrypted = encoder.encode((cryptoutil.frombits(bits),x))
    elif (net.encPref == "Paillier"):
        #encrypt a JSON encoded list of encrypted segments of 12 characters each (converted to ascii)
        encrypted = encoder.encode([str(Paillier.encrypt(net.pubKey,cryptoutil.strToAsciiInt(msg[i:i+12]))) for i in range(0,len(msg),12)])
    elif (net.encPref == "RSA"):
        #encrypt a JSON encoded list of encrypted segments of 20 characters each (converted to ascii)
        encrypted = encoder.encode([str(rsa.encrypt(net.pubKey,cryptoutil.strToAsciiInt(msg[i:i+20]))) for i in range(0,len(msg),20)])
    elif (net.encPref == "AES"):
        #encrypt a JSON encoded list of encrypted segments of 1 character each (converted to ascii)
        AES.keyExp(net.privKey)
        fullInt = str(cryptoutil.strToAsciiInt(msg))
        encrypted = encoder.encode([str(AES.encrypt(int(fullInt[i:i+3]))) for i in range(0,len(fullInt),3)])
    #add the mac to the encrypted message
    encrypted = encoder.encode([encrypted,hashing.hmac(net.macKey, encrypted.encode("utf-8"))])
    print("encrypting: {0} becomes: {1}".format(msg,encrypted))
    return encrypted

"""
decrypt a msg using the current selected encryption algorithm
@param msg: the message to decrypt
@returns the decrypted message
""" 
def decryptMsg(msg):
    #separate and test the mac
    msg,mac = decoder.decode(msg)
    myCalcdMac = hashing.hmac(net.macKey, msg.encode("utf-8"))
    if (mac!=myCalcdMac):
        print("Error: macs do not match! recv'd: {0}, calc'd: {1}".format(mac,myCalcdMac))
        if (disconnect()):
            net.gui.addCloseMessage()
            return ""
    else:
        print("macs match! proceeding")
            
    if (net.encPref == "DES"):
        decrypted = cryptoutil.frombits(DES.decrypt(cryptoutil.tobits(msg),DES.defaultKey))
    elif (net.encPref == "BG"):
        bitsStr,x = decoder.decode(msg)
        decrypted = cryptoutil.frombits(BG.BGPDec(cryptoutil.tobits(bitsStr),x,net.privKey.l,net.privKey.m,net.privKey.a,net.privKey.b))
    elif (net.encPref == "Paillier"):
        msg = decoder.decode(msg)
        decrypted = ''.join([cryptoutil.asciiIntToStr(Paillier.decrypt(net.privKey,net.pubKey,int(i))) for i in msg])
    elif (net.encPref == "RSA"):
        msg = decoder.decode(msg)
        decrypted = ''.join([cryptoutil.asciiIntToStr(rsa.decrypt(net.privKey,int(i))) for i in msg])
    elif (net.encPref == "AES"):
        AES.keyExp(net.privKey)
        msg = decoder.decode(msg)
        decrypted = ''.join([cryptoutil.asciiIntToStr(AES.decrypt(int(i))) for i in msg])
    print("decrypting: {0} becomes: {1}".format(msg,decrypted))
    return decrypted

"""
attempt to connect to the currently specified ip and port
@returns: whether or not we initiated a new connection
"""
def connectToServer():
    if (net.outConn or net.inConn):
        print("Error: already engaged in a chat; please disconnect before establishing a new connection")
        return False
    try:
        net.outSock.settimeout(10)
        net.outSock.connect((net.outIp, net.outPort))
        net.outSock.settimeout(None)
    except:
        print("error: socket timed out. please check your ip/port and try again")
        return False
    print("established outgoing connection")
    net.outConn = net.outSock
    secureConnection(False)
    return True
   
"""
disconnect from the currently active chat, if one exists
@returns: whether or not we disconnected from a connection
""" 
def disconnect():
    if (not (net.inConn or net.outConn)):
        #no connection from which to disconnect5
        return False
    
    if (net.inConn):
        net.inConn.close()
        net.inConn = None
        print("disconnected net.inConn")

    if (net.outConn):
        net.outConn.close()
        net.outConn = None
        net.outSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("disconnected net.outConn")  
    return True
   
"""
secure the current connection, negotiating and establishing a secure channel. Must complete before chat messages may be sent/recvd.
@param amServer: whether we are acting as the server (true) or the client (false) in this instance
"""
def secureConnection(amServer):
    net.securingConnection = True
    print("securing connection as {0}".format("server" if amServer else "client"))
    secureConnectionThread = threading.Thread(target=secureConnectionServer if amServer else secureConnectionClient, args=())
    secureConnectionThread.setDaemon(True)
    secureConnectionThread.start()
    
"""
decide on preferences by picking the first match of PKC and Enc
@param inPKCList: the received list of PKC preferences
@param inEncList: the received list of encryption preferences
@returns; whether common preferences were found and selected (True) or no commonality was found (False)
"""
def decidePreferences(inPKCList,inEncList):
    net.kDistPref = None
    net.encPref = None
    for pref in inPKCList:
        if (pref in net.kDistPrefList):
            net.kDistPref = pref
            break
    for pref in inEncList:
        if (pref in net.encPrefList):
            net.encPref = pref
            break
    return net.kDistPref != None and net.encPref != None
    
"""
daemon thread who runs through securing the connection as the server (person who received connection request)
"""
def secureConnectionServer():
    try:
        #negotiation
        data = net.inConn.recv(net.BUFFER_SIZE).decode("utf-8")
        print("received preference packet is: {0}".format(data))
        data = decoder.decode(data[6:])
        #TODO: don't assume we have the same preference + version
        if not (decidePreferences(data[0],data[1])):
            print("Error: no commonality between preferences")
            disconnect()
            net.gui.addCloseMessage()
            net.securingConnection = False
            return False
        sendMessage("Hello2 {0} {1}".format(net.kDistPref,net.encPref),False)
        data = net.inConn.recv(net.BUFFER_SIZE).decode("utf-8")
        if (data[:9] != "Hello ACK"):
            disconnect()
            net.gui.addCloseMessage()
            net.securingConnection = False
            return False
        establishSecureChannel(True)
    except Exception as ex:
        print("Error: failed to secure a connection, likely experienced network issues; please try again. errorMsg: {0}".format(ex))
        disconnect()
        net.gui.addCloseMessage()
        net.securingConnection = False
        return False
   
"""
daemon thread who runs through securing the connection as the client (person who sent connection request)
""" 
def secureConnectionClient():
    try:
        #negotiation
        sendMessage("Hello {0}".format(encoder.encode([net.kDistPrefList,net.encPrefList])),False)
        data = net.outConn.recv(net.BUFFER_SIZE).decode("utf-8")
        if (data[:6] != "Hello2"):
            disconnect()
            net.gui.addCloseMessage()
            net.securingConnection = False
            return False
        data = data.split(" ")
        net.kDistPref = data[1]
        net.encPref = data[2]
        sendMessage("Hello ACK",False)
        establishSecureChannel(False)
    except Exception as ex:
        print("Error: failed to secure a connection, likely experienced network issues; please try again. errorMsg: {0}".format(ex))
        disconnect()
        net.gui.addCloseMessage()
        net.securingConnection = False
        return False
    
"""
attempt to establish a secure channel; this should only be called during secureConnection
@param amServer: whether I'm the server (True) or the client (False)
"""
def establishSecureChannel(amServer):
    print("~PREFERENCES~\n{0} {1}".format(net.kDistPref,net.encPref))
    net.gui.addSecuringMessage()
    #establishing a secure channel
    if (net.kDistPref == "RSA"):
        net.pubKey,net.privKey = rsa.RSA(net.inConn if amServer else net.outConn,amServer)
    elif (net.kDistPref == "NS_DH"):
        net.privKey = NS_DH.diffieHellman(net.inConn if amServer else net.outConn,amServer)
    #generate additional private / public key data required by the preferred encryption cipher
    if (net.kDistPref == "RSA"):
        #if we're using RSA for key distribution, send one additional encrypted message to agree on a random seed for cipher key gen
        if (amServer):
            random.seed(net.privKey[1])
            rsaSeed = random.randint(0,999999999999)
            net.inConn.send(str(rsa.encrypt(net.pubKey,rsaSeed)).encode("utf-8"))
            random.seed(rsaSeed)
        else:
            random.seed(rsa.decrypt(net.privKey,int(net.outConn.recv(net.BUFFER_SIZE).decode("utf-8"))))
    else:
        random.seed(net.privKey)
    #set mac auth key
    if (net.kDistPref == "RSA"):
        net.macKey = str(random.randint(0,999999999999)).encode("utf-8")
    else:
        net.macKey = str(net.privKey).encode("utf-8")

    if (net.encPref == "Paillier"):
        net.privKey,net.pubKey = Paillier.generate_keypair()
    elif (net.encPref == "BG"):
        net.privKey = BG.generateKey()
    elif (net.encPref == "AES"):
        net.privKey = random.randint(0,999999999999)
    elif (net.encPref == "RSA"):
        if (net.kDistPref != "RSA"):
            #if we are using RSA encryption but not RSA key distribution, generate an rsa priv/pub key pair from seeded random
            net.pubKey,net.privKey = rsa.RSA(0,0,True)
    
    print("{0} secured connection with private key {1} public key {2}".format("server" if amServer else "client",net.privKey,net.pubKey))
    net.securingConnection = False
    net.gui.addChatReadyMessage()
    
"""
daemon thread who listens for messages while we have an active chat, and adds them to the chat history box
"""
def awaitMessages():
    while (True):
        #avoid a busyloop by only checking if we're in an established connection once every 100ms
        time.sleep(.1)
        if ((not net.securingConnection) and (net.inConn or net.outConn)):
            print("awaiting {0} data".format("net.inConn" if net.inConn else "net.outConn"))
            try:
                data = net.inConn.recv(net.BUFFER_SIZE) if net.inConn else net.outConn.recv(net.BUFFER_SIZE)
                print("data packet received is: {0}".format(data))
                if (not data):
                    if (net.inConn):
                        net.inConn.close()
                        net.inConn = None
                    else:
                        net.outConn.close()
                        net.outConn = None
                net.gui.addReceivedMessage(decryptMsg(data.decode("utf-8")))
            except:
                #received an error on conn recv - likely a disconnect was staged; disconnecting
                if (disconnect()):
                    net.gui.addCloseMessage()
    
"""
daemon thread who listens for incoming connections, accepting them if we are not currently in a chat
"""     
def awaitConnections():
    inSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    inSock.bind((net.inIp, net.inPort))
    inSock.listen(1)
    while (True):
        #avoid a busyloop by only checking if we're in a connection once every 100ms
        if (net.inConn or net.outConn):
            time.sleep(.1)
            continue
        net.inConn, addr = inSock.accept()
        '''if (net.outConn):
            #if we just received a connection but we're already chatting on net.outConn, drop the new connection immediately
            net.inConn.close()
            net.inConn = None
        else:'''
        net.gui.addInitMessage()
        print("accepted incoming connection from net.inConn {0}\nnet.outConn {1}".format(net.inConn,addr))     
        secureConnection(True)
        
"""
extract the user's preference data from preferences.cfg
"""
def loadPreferences():
    f = open("preferences.cfg", "r")
    if f.mode != 'r':
        print("Error: preferences file was not found; did you delete it?")
        sys.exit()
    text = f.read()
    f.close()
    prefs = text.strip().split('\n')
    kDistInd = prefs.index("key distribution:")
    encInd = prefs.index("encryption:")
    net.kDistPrefList = [i for i in prefs[kDistInd+1:encInd] if i!='']
    net.encPrefList = [i for i in prefs[encInd+1:] if i!='']

if __name__=='__main__':
    preferences = loadPreferences()
    net.inPort = int(sys.argv[1]) if (len(sys.argv) > 1) else 5005
    net.outPort = int(sys.argv[2]) if (len(sys.argv) > 2) else 5005
    if (len(sys.argv) > 3):
        net.inIp = "127.0.0.1"
    print("initializing with inPort {0} outPort {1}\nkDistPrefs: {2}\nencPrefs: {3}".format(net.inPort,net.outPort,net.kDistPrefList,net.encPrefList))
    #networked threads are essentially daemons bound to the GUI; once the window is closed or an event generates a critical error, all will die
    inConnThread = threading.Thread(target=awaitConnections, args=())
    inMsgThread = threading.Thread(target=awaitMessages, args=())
    inConnThread.setDaemon(True)
    inMsgThread.setDaemon(True)
    inConnThread.start()
    inMsgThread.start()
    GUI.start()