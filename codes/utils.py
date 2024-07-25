import matplotlib.pyplot as plt
import json
import re
import time
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import linregress
from pydub import AudioSegment
import os
import requests

def get_duration(filename):
    audio = AudioSegment.from_file(filename)
    return audio.duration_seconds


def chat_completions(
    client,
    messages,
    model,
    temperature=0.5,
    max_tokens=1024,
    top_p=1,
    stop=None,
    stream=False,
):
    return (
        client.chat.completions.create(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            stream=stream,
        )
        .choices[0]
        .message.content
    )


def extract_list_from_string(log_string):
    match = re.search(r"\[.*\]", log_string)
    if match:
        start_index = match.start()
        end_index = log_string.rindex("]") + 1
        list_str = log_string[start_index:end_index]
        return json.loads(list_str)
    else:
        return None


def extract_messages_from_json(json_path) -> list:
    result = []
    with open(json_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    for i in range(len(data)):
        text_payload = data[i]["textPayload"]
        try:
            payload_list = extract_list_from_string(text_payload)
            if payload_list == None:
                continue
        except Exception as e:
            continue
        result.append(payload_list)
    return result


def plot_model_comparison(results: dict):
    models = [result['model'] for result in results]
    avg_times = [result['avg_time'] for result in results]
    avg_wer = [result['avg_wer'] for result in results]
    query_len_vs_wer = [result['query_len_vs_wer'] for result in results]
    fail_rates = [result['fail'] / result['overall_query'] for result in results]
    query_len_vs_time = [result['query_len_vs_time'] for result in results]
    model_colors = {
        'llama3-70b-8192': 'blue',
        'gpt-3.5-turbo-0125': 'green',
        'gpt-4o-2024-05-13': 'orange',
        'whisper-large-v3': 'red',
        'whisper-1': 'purple',
        "nova-2-general": "black",
        "whisper": "pink",
    }


    # first graph: average time comparison
    def avg(input, title):
        plt.figure(figsize=(10, 6))
        plt.bar(models, input, color=[model_colors[model] for model in models])
        plt.xlabel('Model')
        plt.ylabel('Y Viariable')
        plt.title(title)
        plt.show()
    
    # second graph: failure rate comparison
    def fail(input, title=None):
        plt.figure(figsize=(10, 6))
        plt.bar(models, input, color=[model_colors[model] for model in models])
        plt.xlabel('Model')
        plt.ylabel('Failure Rate')
        plt.title('Failure Rate Comparison')
        plt.show()
    
    # third graph: query length vs time taken with regression lines
    def growth(input, title):
        plt.figure(figsize=(10, 6))

        for model, qlt in zip(models, input):
            query_lengths = np.array(list(qlt.keys()))
            times = np.array([sum(times_list) / len(times_list) for times_list in qlt.values()])
            plt.scatter(query_lengths, times, label=model, color=model_colors[model])
            
            # Calculate and plot regression line
            slope, intercept, r_value, p_value, std_err = linregress(query_lengths, times)
            line = slope * query_lengths + intercept
            plt.plot(query_lengths, line, color=model_colors[model], label=f'{model} regression')

        plt.xlabel('Query Length')
        plt.ylabel('Y Variable')
        plt.title(title)
        plt.legend()
        plt.show()

    avg(avg_times, "Average Time Comparison")
    avg(avg_wer, "Average WER")
    fail(fail_rates)
    growth(query_len_vs_wer, "Query Len vs WER")
    growth(query_len_vs_time, "Query Len vs Time")


def non_concurrent_test(testing_messages: list, testing_client, testing_model: str):
    query_len_vs_time = {}
    overall_time = 0
    overall_query = 0
    success = 0
    fail = 0
    for i in range(len(testing_messages)):
        try:
            testing_message = testing_messages[i]
            query_length = sum([len(message["content"]) for message in testing_message])
            start_time = time.time()
            result = chat_completions(
                testing_client,
                testing_message,
                testing_model,
            )
            end_time = time.time()
            time_taken = end_time - start_time
            if len(result) == 0:
                fail += 1
                continue
            else:
                success += 1
                overall_time += time_taken
                overall_query += query_length
                query_len_vs_time[query_length] = [time_taken]
        except Exception as e:
            print(f"Test number: {i}, failed due to {e}")
            fail += 1

        if i % 10 == 0 and i != 0:
            print(f"Test number: {i}, stop to prevent rate limit")
            time.sleep(60)

    avg_time = overall_time / success if success != 0 else 0

    result = {}
    result["model"] = testing_model
    result["avg_time"] = avg_time
    result["success"] = success
    result["fail"] = fail
    result["overall_query"] = overall_query
    result["query_len_vs_time"] = query_len_vs_time
    return result

def stt_test(testing_files, testing_texts, testing_client, testing_model):
    query_len_vs_time = {}
    query_len_vs_wer = {}
    overall_wer = 0
    overall_time = 0
    overall_query = 0
    success = 0
    fail = 0
    i = 0
    for testing_file in testing_files:
        with open(testing_file, "rb") as file:
            if testing_model in ["whisper-1", "whisper-large-v3"]:
                start_time = time.time()
                transcription = testing_client.audio.transcriptions.create(
                    file=(testing_file, file.read()),
                    model=testing_model,
                )
                end_time = time.time()
                time_taken = end_time - start_time
                try:
                    wer = calculate_wer(testing_texts[i], transcription.text)
                except Exception as e:
                    print(f"Test number: {i}, failed due to {e}")
                    fail += 1
                    i += 1
                    continue
            else:
                url = f'https://api.deepgram.com/v1/listen?model={testing_model}&detect_language=true'
                headers = {
                    "Authorization": f"Token 426f8c51a2dfe9aecbb744d6af986118ed40026f",
                    "Content-Type": "audio/*",
                }
                start_time = time.time()
                response = requests.post(url=url, headers=headers, data=file)
                end_time = time.time()
                alter = response.json()['results']['channels'][0]['alternatives']
                if len(alter) == 0 and "empty" not in testing_file:
                    fail += 1
                    i += 1
                    continue
                elif len(alter) == 0:
                    transcript = ""
                else:
                    transcript = alter[0]['transcript']
                    
                time_taken = end_time - start_time
                try:
                    wer = calculate_wer(testing_texts[i], transcript)
                except Exception as e:
                    print(f"Test number: {i}, failed due to {e}")
                    fail += 1
                    i += 1
                    continue
        success += 1
        overall_wer += wer
        overall_time += time_taken
        overall_query += get_duration(testing_file)
        query_len_vs_time[get_duration(testing_file)] = [time_taken]
        query_len_vs_wer[get_duration(testing_file)] = [wer]
        i += 1
        if i % 10 == 0 and i != 0:
            print(f"Test number: {i}, stop to prevent rate limit")
            time.sleep(30)

    avg_time = overall_time / success if success != 0 else 0
    result = {}
    result["model"] = testing_model
    result["avg_time"] = avg_time
    result["success"] = success
    result["fail"] = fail
    result["overall_query"] = overall_query
    result["query_len_vs_time"] = query_len_vs_time
    result["query_len_vs_wer"] = query_len_vs_wer
    result["avg_wer"] = overall_wer / success if success != 0 else 0
    return result
            
from jiwer import wer

def calculate_wer(reference, hypothesis):
    print(reference, hypothesis)
    if len(reference) == 0:
        return 0 if len(hypothesis) == 0 else 1
    return wer(reference, hypothesis)



