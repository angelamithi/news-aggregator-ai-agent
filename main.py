import openai
from dotenv import find_dotenv,load_dotenv
import logging
import time
from datetime import datetime
import os
import requests
import json
import streamlit as st

# Load secrets from Streamlit Secrets
openai_api_key = st.secrets["OPENAI_API_KEY"]

# Initialize the OpenAI client with the API key
openai.api_key = openai_api_key
client = openai.OpenAI(api_key=openai.api_key)
model = "gpt-3.5-turbo-16k"
news_api_key = st.secrets["NEWS_API_KEY"]


def get_news(topic):
    url=(
        f"https://newsapi.org/v2/everything?q={topic}&from=2024-03-10&sortBy=publishedAt&apiKey={news_api_key}&pageSize=5"
    )
    try:
        response=requests.get(url)
        if response.status_code==200:
            news=json.dumps(response.json(), indent=4)
            news_json=json.loads(news)

            data=news_json
            # Access all the fields 
            status=data["status"]
            total_results=data["totalResults"]
            articles=data["articles"]
            final_news=[]

            # Loop through the article
            for article in articles:
                source_name=article["source"]["name"]
                author=article["author"]
                title=article["title"]
                description=article["description"]
                url=article["url"]
                content=article["content"]

                title_description=f"""
                Title:{title}
                Author:{author}
                Source:{source_name}
                Description:{description}
                URL:{url}
       
                """
                final_news.append(title_description)
            return final_news
        else:
            return []
        


    except requests.exceptions.RequestException as e:
        print("Error Occurred during Api Requests",e)

class AssistantManager:
    thread_id=None
    assistant_id=None

    def __init__(self,model:str=model):
        self.client=openai.OpenAI()
        self.model=model
        self.assistant=None
        self.thread=None
        self.run=None
        self.summary=None

        # Retrieve existing assistant and thread if IDs are already set

         # Retrieve existing assistant and thread if IDs are stored in session state
        if st.session_state.assistant_id:
            self.assistant = self.client.beta.assistants.retrieve(
                assistant_id=st.session_state.assistant_id
            )
        if st.session_state.thread_id:
            self.thread = self.client.beta.threads.retrieve(
                thread_id=st.session_state.thread_id
            )

    def create_assistant(self,name,instructions,tools):
        if not self.assistant:
            assistant_obj=self.client.beta.assistants.create(
                name=name,
                instructions=instructions,
                tools=tools,
                model=self.model
            )
            AssistantManager.assistant_id=assistant_obj.id
            self.assistant=assistant_obj# This is now our new assisant
            print(f"AssisID:::: {self.assistant.id}")

    def create_thread(self):
        if not self.thread:
            thread_obj = self.client.beta.threads.create()
            self.thread = thread_obj  # This sets the local thread instance
            st.session_state.thread_id = thread_obj.id  # Save the thread ID in session state
            print(f"ThreadID:::: {self.thread.id}")

    def add_message_to_thread(self,role,content):
        if self.thread:
            self.client.beta.threads.messages.create(
                thread_id=self.thread.id,
                role=role,
                content=content
        )
    def run_assistant(self,instructions):
        if self.assistant and self.thread:
            self.run=self.client.beta.threads.runs.create(
                thread_id=self.thread.id,
                assistant_id=self.assistant.id,
                instructions=instructions

            )
    def process_message(self):
        if self.thread:
            messages=self.client.beta.threads.messages.list(thread_id=self.thread.id)
            summary=[]
            last_message=messages.data[0]
            role=last_message.role
            response=last_message.content[0].text.value
            summary.append(response)
            self.summary="\n".join(summary)
            print(f"SUMMARY-----> {role.capitalize()}: ==> {response}")
    

    def wait_for_completion(self):
        if self.thread and self.run:
            while True:
                time.sleep(5)
                run_status=self.client.beta.threads.runs.retrieve(
                    thread_id=self.thread.id,
                    run_id=self.run.id
                )
                print(f"RUN STATUS::{run_status.model_dump_json(indent=4)}")
                if run_status.status=="completed":
                    self.process_message()
                    break
                elif run_status.status=="requires_action":
                    print("FUNCTION CALLING NOW....")
                    self.call_required_functions(required_actions=run_status.required_action.submit_tool_outputs.model_dump())
            

    def call_required_functions(self,required_actions):
        if not self.run:
            return
        tool_outputs=[]
        for action in required_actions["tool_calls"]:
            func_name=action["function"]["name"]
            arguments=json.loads(action["function"]["arguments"])
            if func_name=="get_news":
                output=get_news(topic=arguments["topic"])
                print(f"STUFFFFF;;;;{output}")
                final_str=""
                for item in output:
                    final_str +="".join(item)
                tool_outputs.append({"tool_call_id":action["id"],
                                    "output": final_str})
            else:
                raise ValueError(f"Unknown Function:{func_name}")
        print("Submitting outputs back to the Assistant...")
        self.client.beta.threads.runs.submit_tool_outputs(
            thread_id=self.thread.id,
            run_id=self.run.id,
            tool_outputs=tool_outputs


        )
    #streamlit
    def get_summary(self):
        return self.summary

    def run_steps(self):
        if not self.thread:
            print("No thread available")
            return []
    
        run_steps = self.client.beta.threads.runs.steps.list(
            thread_id=self.thread.id,
            run_id=self.run.id
        )
        print(f"Run-Steps::: {run_steps}")
        return run_steps.data


        
def main():
    st.title("News Summarizer")

    if 'assistant_id' not in st.session_state or 'thread_id' not in st.session_state:
        st.session_state.assistant_id = None
        st.session_state.thread_id = None

    with st.form(key="user_input_form"):
        instructions = st.text_input("Enter topic:")
        submit_button = st.form_submit_button(label="Run Assistant")

        if submit_button:
            manager = AssistantManager()
            if not st.session_state.assistant_id:
                manager.create_assistant(
                    name="News Summarizer",
                    instructions="You are a personal article summarizer Assistant who knows how to take a list of article's titles and descriptions and then write a short summary of all the news articles",
                    tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "get_news",
                            "description": "Get the list of articles/news for the given topic",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "topic": {
                                        "type": "string",
                                        "description": "The topic for the news, e.g. bitcoin",
                                    }
                                },
                                "required": ["topic"],
                            },
                        },
                    }
                ],
                )
                st.session_state.assistant_id = manager.assistant.id
            
            if not st.session_state.thread_id:
                manager.create_thread()
                st.session_state.thread_id = manager.thread.id

            # Add the message and run the assistant
            manager.add_message_to_thread(
                role="user",
                content=f"summarize the news on this topic {instructions}?"
            )
            manager.run_assistant(instructions="Summarize the news")
            # Wait for completions and process messages
            manager.wait_for_completion()
            summary = manager.get_summary()
            st.write(summary)
            st.text("Run Steps:")
            st.code(manager.run_steps(), line_numbers=True)

if __name__ == "__main__":
    main()



