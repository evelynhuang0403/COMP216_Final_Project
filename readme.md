Networking for Software Developers
This is the final project of COMP216. It is a group effort that will replace your second test and will contribute 30% towards your final grade. This builds on the previous week’s labs, which may require some tweaking to assemble into a complete IoT solution. We will discuss a mutually convenient submission date.
Before You Start
This is a large undertaking considering the time constraints and the number of components required. One person would not be able to and should not be completing all the work because of the volume and the scope. Because the time is not sufficient for one person to adequately complete all the prescribed tasks. 
I suggest short (not more than 15 minutes) meetings frequently (at least 5 times per week), where designs are finalized, tasks are farmed out, and reported back on. You can also examine the milestones and see if more effort is needed to bring any lagging tasks up to the expected completeness.
Make use of your favourite collaboration platform: WhatsApp™, Discord™, Slack™, Signal™, Telegram™, Teams™, etc. and relegate e-mails to formal correspondence.
Intellectual Property
Software ownership is intellectual property. It is critical to understand that you may not take credit for something that you do not own/create. If you use code, algorithms or ideas from somewhere, it is ethical and the right thing to acknowledge the owner of the intellectual property. For this course, if this happens, then you are committing plagiarism, and punishment can range from a reprimand to a failing grade to expulsion.
Technical Constraints
You will only use the libraries that were covered in classes. You will use Python version 3.9 or later. The only external frameworks/libraries allowable are Requests, Flask, and Mosquito. You may use the libraries in a standard Python distribution (discussed in the course).
You must use 90% of the code from your previous labs.
Overview
We will implement an end-to-end IoT solution that will satisfy the client's needs (this is based on your previous labs). We will use the MQTT protocol for this implementation. There will be publisher clients that send data to a broker, as well as subscriber clients that receive data from the broker. The broker sends data to the appropriate subscriber. 
You will design and build both types of clients according to specifications. The diagram shows an overly simplified architecture of the intended system.


Each component is described more fully below, along with the weight contribution towards the final grade. Each component must be implemented as a well-designed class.
Summary Rubric
The weight includes the design, implementation, and demonstration of a particular component.
No written documentation is required, only your Python code files. Your source files should have only one class per file.
Item	Marks (%)
Broker	5
Publisher	40
Subscriber	45
Quality of code	5
Video (demonstration)	5
Total	100
Bonus	20
Detailed Description
Broker
You will install the Eclipse mosquito broker or leverage a cloud-based broker and ensure that it is working as expected.

Publisher
The publisher will generate data to send to the broker at regular intervals. The data value must be random with a pattern (I know that this is a contradiction). Think of the value of a particular stock on the stock exchange or the outdoor temperature around your home. 
This must be implemented as a GUI and must include an interface to change the various parameters of this publisher.


You will configure and run multiple publisher clients to simulate multiple devices.
Publisher – Value generation
This must be implemented in a class in a separate file. (Just import the filename without the .py extension in the file where you want to use the logic). This must be based on Lab Assignment 7 – Part II. You must not limit the number of values generated.
The design should be such that it is easy to use and flexible enough to give the data value in the required pattern.
[Similar to the specifications of Lab Assignment 7 – Part II, more rigidly enforced]
Publisher – Packaging the above values
The above value must be tagged with at least a time stamp packet ID and packaged as a JSON object before transmission. You decide what other features you need to encapsulate in your package. [See util.py]
Publisher – Sending data to broker
•	You will send the above-packaged data to the broker under an agreed topic. [See publisher.py]
•	You must miss transmission with a frequency of about 1 in every 100 transmissions. This must not be deterministic!
Publisher – Extras
These extras are for bonus points and will only be considered if all the normal specifications are satisfied adequately.
•	To simulate a real-world scenario, occasionally skip blocks of transmissions (or sets of transmissions). This condition must not throw the subscriber into confusion.
•	Transmit "wild data value" that is completely off the chart. Again, your subscriber should be able to handle this.
•	Anything that will add value to your project. You must make me aware of these.
 
Subscriber
The subscribers accept data from the broker and process it. It will decode the data and decide how to process it. This is best implemented as a GUI application. [Similar to the specifications of Lab Assignment 9]
You will configure and run multiple subscriber clients to simulate multiple devices.
Subscriber – Receiving data from the broker
•	Listen to messages from the broker under an agreed topic.
•	Decode the message and decide how to handle the data.
Subscriber – Handling the data/absence of data
This section is important because this is where you imbue your personality on this project. You must decide what is out-of-range data. You also must be able to detect missing transmission. 
•	Handle sensible data. Display data both in text and visual formats.
•	Detecting and handling out-of-range (erroneous) data. 
•	Detecting and handling missing data.
•	Implementation of SMTP functionality to send email notifications in the event of erroneous or missing data. [Similar to the specifications of Lab Assignment 8 – Part II]
Subscriber – Extras
These extras are for bonus points and will only be considered if all the normal specifications are satisfied adequately.
•	To simulate a real-world scenario, occasionally skip blocks of transmissions (or sets of transmissions).
•	User-accessible controls to unsubscribe from and resubscribe to a designated topic.
•	Anything that will add value to your project. You must make me aware of these.

Bonus
Implement Flask API services to introduce new platform enhancements that support the management of the publisher(s) and subscriber(s).
This is best implemented as a separate Flask server and GUI application, supporting the work of an IT administrator.
Flask API Services – Extras
•	Search historical data and display graphical output based on a selected range.
•	Export logs from the last 5 – 10 anomalies and provide aggregate statistics.
•	Set reporting period(s) or operational schedule (e.g., scheduled pause or start periods for publishers and/or subscribers, shutdown publisher and/or subscriber for maintenance, etc.).
•	Dynamically configure and update MQTT configurations (e.g., enable legacy support via MQTT v3, force only MQTT v5 messaging, change QoS level, etc.).
•	Log and display service-level data related to the message streams sent to the subscribers (e.g., QoS, schema, etc.).

Quality of Code
These 5 points are to lose. You automatically start with full points, and as the instructor notices code aberration, these 5 points will evaporate. Code aberration will include design flaws and implementation blunders.
Video of Project
You make a 15 – 20-minute video that will demonstrate each of the items in the rubric table. If an item is not clearly demonstrated, there might be a possibility that you might not get a point for that item.
You need not demonstrate the quality of the code.

Due: 
See the schedule for the due date.
 
Submission
1.	You will bundle all your files (except the video) into a single zip file (not .rar or anything else). The name of the file will be group_«your_group_number».zip e.g., group_1.zip.
2.	Your publisher code files must be called group_«your_group_number»_publisher.py e.g., group_1_publisher.py.
3.	Your subscriber code files must be called group_«your_group_number»_subscriber.py e.g., group_1_subscriber.py.
4.	All your other code files must be prefixed by your group number e.g., group_1_data_generator.py
5.	Must be uploaded to the course drop box.
6.	The video file must be uploaded directly to the drop box following the same naming conventions.
