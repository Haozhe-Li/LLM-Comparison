import matplotlib.pyplot as plt
import json
import re
import time
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import linregress


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


def plot_model_comparison(results):
    models = [result['model'] for result in results]
    avg_times = [result['avg_time'] for result in results]
    fail_rates = [result['fail'] / result['overall_query'] for result in results]
    query_len_vs_time = [result['query_len_vs_time'] for result in results]
    model_colors = {
        'llama3-70b-8192': 'blue',
        'gpt-3.5-turbo-0125': 'green',
        'gpt-4o-2024-05-13': 'orange'
    }
    
    # first graph: average time comparison
    plt.figure(figsize=(10, 6))
    plt.bar(models, avg_times, color=[model_colors[model] for model in models])
    plt.xlabel('Model')
    plt.ylabel('Average Time (s)')
    plt.title('Average Time Comparison')
    plt.show()
    
    # second graph: failure rate comparison
    plt.figure(figsize=(10, 6))
    plt.bar(models, fail_rates, color=[model_colors[model] for model in models])
    plt.xlabel('Model')
    plt.ylabel('Failure Rate')
    plt.title('Failure Rate Comparison')
    plt.show()
    
    # third graph: query length vs time taken with regression lines
    plt.figure(figsize=(10, 6))

    for model, qlt in zip(models, query_len_vs_time):
        query_lengths = np.array(list(qlt.keys()))
        times = np.array([sum(times_list) / len(times_list) for times_list in qlt.values()])
        plt.scatter(query_lengths, times, label=model, color=model_colors[model])
        
        # Calculate and plot regression line
        slope, intercept, r_value, p_value, std_err = linregress(query_lengths, times)
        line = slope * query_lengths + intercept
        plt.plot(query_lengths, line, color=model_colors[model], label=f'{model} regression')

    plt.xlabel('Query Length')
    plt.ylabel('Time Taken (s)')
    plt.title('Query Length vs Time Taken')
    plt.legend()
    plt.show()

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

    avg_time = overall_time / success

    result = {}
    result["model"] = testing_model
    result["avg_time"] = avg_time
    result["success"] = success
    result["fail"] = fail
    result["overall_query"] = overall_query
    result["query_len_vs_time"] = query_len_vs_time
    return result



