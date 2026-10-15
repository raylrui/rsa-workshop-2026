## Application Requirements

This is a simple streamlit application that presents a window backed by Bedrock. Its purpose is to show how simple a Bedrock-powered LLM document classification application can be.

The application should show a simple window that allows the user to upload a PDF document. Once a document is uploaded, the window should show a Classify button. When it's pressed, the document is sent to the Bedrock LLM with the following system prompt:

You are a patent examiner familiar with the International Patent Classification (IPC). I am going to give you a patent application. I want you to examine the patent application and classify the patent according to the IPC. Explain your reasoning and tell me the classification.

Store the system prompt in a separate config file so the users can easily adjust it.

The window should then display the LLM's answer. Display some kind of progress/loading indicator while the LLM is thinking as the document might be quite large.

The application is designed to be run within the AWS environment, so it can take advantage of the instance role on the container or EC2 it's running on, and no additional auth is required.

The application should be configured to use the inference profile ID for the Claude Haiku 4.5 (or newer) in us-east-1.

## Prerequisites - Configuration

* Install the dependencies listed in the `requirements.txt` file using pip. You can run the following command in your local terminal:
```bash
$ pip install -r requirements.txt
```

## Usage
* Run the Streamlit application by executing the command below in your local system terminal:

```bash
$ streamlit run doc.py --server.port 8081
```

**Note: In Code Editor port 8080 is in use already, so use port 8081**

* Open your web browser and go to the URL provided by Streamlit, usually http://localhost:8081. In Code Editor, click the "Open in Browser" pop-up that appears, or use the "Ports" tab in the lower pane to open the application.

* Interact with the application as desired.
