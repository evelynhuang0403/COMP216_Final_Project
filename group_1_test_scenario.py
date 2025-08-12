#!/usr/bin/env python3
"""
Test scenario script to demonstrate No Data Feed and Network Drop detection
This script helps test the subscriber's ability to detect:
1. No Data Feed - when publisher is connected but stops sending data
2. Network Drop - when publisher goes offline (LWT message)
"""

import subprocess
import sys
import time
import threading
from tkinter import *
from tkinter import messagebox

class TestScenarioController:
    def __init__(self, master):
        self.master = master
        self.master.title("Group 1 - Test Scenario Controller")
        self.master.geometry("600x400")
        
        self.publisher_process = None
        self.subscriber_process = None
        
        self.setup_ui()
    
    def setup_ui(self):
        # Title
        title_label = Label(self.master, text="IoT Test Scenario Controller", 
                           font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        # Instructions
        instructions = """
This controller helps test the subscriber's detection capabilities:

1. No Data Feed Detection:
   - Start publisher and subscriber
   - Use 'Stop Publishing' button in publisher (keeps connection)
   - Subscriber should detect "NO DATA FEED" after 10 seconds

2. Network Drop Detection:
   - Start publisher and subscriber
   - Use 'Drop Connection' button in publisher OR close publisher window
   - Subscriber should detect "NETWORK DROP" from LWT message
        """
        
        instruction_label = Label(self.master, text=instructions, 
                                justify=LEFT, font=("Arial", 10))
        instruction_label.pack(pady=10, padx=20)
        
        # Control buttons
        button_frame = Frame(self.master)
        button_frame.pack(pady=20)
        
        # Start publisher button
        self.start_pub_btn = Button(button_frame, text="Start Publisher (dev001)", 
                                   command=self.start_publisher,
                                   bg="#4CAF50", fg="white", font=("Arial", 11, "bold"),
                                   width=20)
        self.start_pub_btn.pack(pady=5)
        
        # Start subscriber button
        self.start_sub_btn = Button(button_frame, text="Start Subscriber", 
                                   command=self.start_subscriber,
                                   bg="#2196F3", fg="white", font=("Arial", 11, "bold"),
                                   width=20)
        self.start_sub_btn.pack(pady=5)
        
        # Status frame
        status_frame = LabelFrame(self.master, text="Process Status", font=("Arial", 11, "bold"))
        status_frame.pack(fill=X, padx=20, pady=10)
        
        self.pub_status = Label(status_frame, text="Publisher: Stopped", fg="red")
        self.pub_status.pack(anchor=W, padx=10, pady=2)
        
        self.sub_status = Label(status_frame, text="Subscriber: Stopped", fg="red")
        self.sub_status.pack(anchor=W, padx=10, pady=2)
        
        # Test scenarios frame
        test_frame = LabelFrame(self.master, text="Quick Test Actions", font=("Arial", 11, "bold"))
        test_frame.pack(fill=X, padx=20, pady=10)
        
        test_instructions = Label(test_frame, 
                                text="After starting both processes, use the publisher UI to test scenarios:",
                                font=("Arial", 9))
        test_instructions.pack(anchor=W, padx=10, pady=2)
        
        test_list = Label(test_frame,
                         text="• Click 'Stop' button: Tests NO DATA FEED detection\n" +
                              "• Click 'Drop Connection': Tests NETWORK DROP detection\n" +
                              "• Close publisher window: Tests NETWORK DROP detection",
                         font=("Arial", 9), justify=LEFT)
        test_list.pack(anchor=W, padx=20, pady=2)
    
    def start_publisher(self):
        if self.publisher_process is None:
            try:
                # Start publisher for dev001
                self.publisher_process = subprocess.Popen([
                    sys.executable, "group_1_publisher.py", "dev001"
                ], cwd=".")
                
                self.pub_status.config(text="Publisher: Running (dev001)", fg="green")
                self.start_pub_btn.config(text="Publisher Running", state=DISABLED)
                
                # Monitor process
                threading.Thread(target=self.monitor_publisher, daemon=True).start()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start publisher: {e}")
    
    def start_subscriber(self):
        if self.subscriber_process is None:
            try:
                # Start subscriber
                self.subscriber_process = subprocess.Popen([
                    sys.executable, "group_1_subscriber.py"
                ], cwd=".")
                
                self.sub_status.config(text="Subscriber: Running", fg="green")
                self.start_sub_btn.config(text="Subscriber Running", state=DISABLED)
                
                # Monitor process
                threading.Thread(target=self.monitor_subscriber, daemon=True).start()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start subscriber: {e}")
    
    def monitor_publisher(self):
        if self.publisher_process:
            self.publisher_process.wait()
            # Process ended
            self.master.after(0, lambda: [
                self.pub_status.config(text="Publisher: Stopped", fg="red"),
                self.start_pub_btn.config(text="Start Publisher (dev001)", state=NORMAL)
            ])
            self.publisher_process = None
    
    def monitor_subscriber(self):
        if self.subscriber_process:
            self.subscriber_process.wait()
            # Process ended
            self.master.after(0, lambda: [
                self.sub_status.config(text="Subscriber: Stopped", fg="red"),
                self.start_sub_btn.config(text="Start Subscriber", state=NORMAL)
            ])
            self.subscriber_process = None
    
    def on_closing(self):
        # Clean up processes
        if self.publisher_process:
            try:
                self.publisher_process.terminate()
                self.publisher_process.wait(timeout=5)
            except:
                try:
                    self.publisher_process.kill()
                except:
                    pass
        
        if self.subscriber_process:
            try:
                self.subscriber_process.terminate()
                self.subscriber_process.wait(timeout=5)
            except:
                try:
                    self.subscriber_process.kill()
                except:
                    pass
        
        self.master.destroy()


if __name__ == "__main__":
    root = Tk()
    app = TestScenarioController(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()