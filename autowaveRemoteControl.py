import socket
from time import sleep
import sys
import os
class AutoWaveConnectionTester:
    STX = 0x02  # Start of Text
    ETX = 0x03  # End of Text
    ACK = 0x06  # Acknowledge
    NACK = 0x15  # Negative Acknowledge
    BUSY = 0x19  # Busy
    NOTREADY = 0x16  # Not Ready
    
    def __init__(self, port=15000):
        self.ip_address = "192.168.x.x"
        self.port = port
        self.timeout = 2  # Increased timeout for network device
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)

        try:
            self.socket.connect((self.ip_address, self.port))
            print(f"Successfully connected to {self.ip_address}:{self.port}")
            
            # Read and discard FTP welcome message
            try:
                welcome = self.socket.recv(4096)
                print(f"FTP Welcome: {welcome.decode('ascii', errors='ignore').strip()}")
                # Wait a bit after receiving welcome
                sleep(0.5)
            except socket.timeout:
                print("No welcome message received (timeout)")
            except Exception as e:
                print(f"Error reading welcome: {e}")
                
        except Exception as e:
            print(f"Failed to connect to {self.ip_address}:{self.port} - {e}")
            self.socket = None
    
    def calculate_checksum(self, data):
        """
        Calculate checksum per AutoWave specification:
        - Sum ASCII codes between STX and ETX
        - If sum <= 0x20, add 0x20 to ensure it's not a control character
        """
        checksum = sum(data) % 256
        if checksum <= 0x20:
            checksum += 0x20
        return checksum
    
    def format_message(self, command_str):
        """Format command as: STX + COMMAND + ETX + CHECKSUM"""
        command_bytes = command_str.encode('ascii')
        checksum = self.calculate_checksum(command_bytes)
        
        message = bytes([self.STX]) + command_bytes + bytes([self.ETX, checksum])
        return message
    
    def debug_checksums(self, command_str):
        """Show checksum calculation for verification"""
        command_bytes = command_str.encode('ascii')
        
        # Sum checksum per documentation
        cs = sum(command_bytes) % 256
        if cs <= 0x20:
            cs += 0x20
        
        return f"0x{cs:02X}"
    
    def parse_response(self, response_bytes):
        """Parse binary response"""
        if not response_bytes:
            return "No response"
        
        # Check for control bytes
        if len(response_bytes) == 1:
            control = response_bytes[0]
            if control == self.ACK:
                return "ACK (Command understood and treated)"
            elif control == self.NACK:
                return "NACK (Command not understood or checksum wrong)"
            elif control == self.BUSY:
                return "BUSY (Command in progress)"
            elif control == self.NOTREADY:
                return "NOTREADY (Cannot accept command)"
        
        # If starts with STX, extract message
        if response_bytes[0] == self.STX:
            try:
                etx_index = response_bytes.index(self.ETX)
                message = response_bytes[1:etx_index].decode('ascii')
                if len(response_bytes) > etx_index + 1:
                    cs = response_bytes[etx_index + 1]
                    return f"{message} [CS: 0x{cs:02X}]"
                return message
            except Exception as e:
                return f"Parse error: {e}"
        
        # Fallback to hex representation
        return " ".join(f"0x{b:02X}" for b in response_bytes)

    def send_with_retry(self, command, max_retries=50, delay=0.1):
        """
        Sends a command and automatically retries if the device returns BUSY.
        """
        if command.startswith('*'):
            message = command.encode('ascii')
        else:
            message = self.format_message(command)

        for attempt in range(max_retries):
            try:
                self.socket.send(message)
                sleep(delay) # Pause between send and receive to give device time to process
                
                response_bytes = self.socket.recv(4096)
                parsed_response = self.parse_response(response_bytes)
                
                if "BUSY" in parsed_response.upper():
                    # Device is busy, loop goes to the next iteration to resend
                    print(f"[{attempt + 1}] Device is busy with '{command}', trying again...")
                    sleep(0.3)
                    continue
                
                # If not BUSY, it succeeded. Returning the response.
                print(f"[SUCCESS] {command} -> {parsed_response}")
                return parsed_response

            except socket.timeout:
                print(f"[TIMEOUT] No response for '{command}' (attempt {attempt + 1})")
                continue
            except Exception as e:
                print(f"[ERROR] Error occurred while sending '{command}': {e}")
                return None
                
        print(f"[END] Giving up on '{command}' after {max_retries} attempts.")
        return None
        
    def reconnect(self, port):
        """Reconnect to device on different port"""
        self.close()
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        try:
            self.socket.connect((self.ip_address, self.port))
            print(f"Successfully connected to {self.ip_address}:{self.port}")
            # Read welcome if available
            try:
                welcome = self.socket.recv(4096)
                print(f"Welcome: {welcome.decode('ascii', errors='ignore').strip()}")
                sleep(0.5)
            except socket.timeout:
                pass
            return True
        except Exception as e:
            print(f"Failed to connect to {self.ip_address}:{self.port} - {e}")
            self.socket = None
            return False
    
    def close(self):
        if self.socket:
            self.socket.close()

    # Additional function to upload file via FTP
    def _upload_file_ftp(self, local_filepath, target_filename):
        """ Sends file to AutoWave FTP server using the built-in ftplib. """
        if not os.path.exists(local_filepath):
            print(f"[FTP ERROR] Local file '{local_filepath}' does not exist!")
            return False

        print(f"\n[FTP 21] Starting file transfer: {target_filename} ...")
        ftp = None
        try:
            ftp = ftplib.FTP(self.ip_address)
            ftp.login('guest', '')
            
            remote_path = f"/home/guest/DowFiles/{target_filename}"
            
            with open(local_filepath, 'rb') as file:
                ftp.storbinary(f"STOR {remote_path}", file)
                
            print(f"[FTP 21] Transfer sucessfull! File saved as: {remote_path}")
            return True
        except Exception as e:
            print(f"[FTP ERROR] Error while sending: {e}")
            return False
        finally:
            if ftp:
                ftp.quit()