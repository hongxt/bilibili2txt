# 导入requests模块，模拟发送请求
import requests
# 导入json
import json
# 导入re
import re
import os
from moviepy.editor import *
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
import time
import torch
import whisper

# A. 视频下载
def download_video_url(url,folder,video_name):
    # 1. 匹配出视频的标题和视频地址
    def my_match(text, pattern):
        match = re.search(pattern, text)
        # print(match.group(1))
        # print()
        return json.loads(match.group(1))
    
    # 2. 发送请求，拿回数据
    headers = {
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36'
    }
    res = requests.get(url, headers=headers)
    playinfo = my_match(res.text, '__playinfo__=(.*?)</script><script>')
    # 视频内容json
    initial_state = my_match(res.text, r'__INITIAL_STATE__=(.*?);\(function\(\)')
    # 视频分多种格式，直接取分辨率最高的视频 1080p
    video_url = playinfo['data']['dash']['video'][0]['baseUrl']
    # 取出音频地址
    audio_url = playinfo['data']['dash']['audio'][0]['baseUrl']
    title = initial_state['videoData']['title']
    print('视频名字为：', title)
    # print('视频地址为：', video_url)
    # print('音频地址为：', audio_url)

    # 3. 下载视频
    # 3.1 创建文件夹
    if not os.path.exists(folder):
        os.makedirs(folder)

    # 3.2 获取大小
    print("开始下载视频：%s" % title)
    headers.update({"Referer": url})
    video_content = requests.get(video_url, headers=headers)
    print('%s视频大小：' % title, float(video_content.headers['content-length']) / 1024 / 1024, 'MB')
    audio_content = requests.get(audio_url, headers=headers)
    print('%s音频大小：' % title, float(audio_content.headers['content-length']) / 1024 / 1024, 'MB')

    # 3.3 下载视频开始
    received_video = 0
    with open(f'{folder}/{video_name}_video.mp4', 'ab') as output:
        while int(video_content.headers['content-length']) > received_video:
            headers['Range'] = 'bytes=' + str(received_video) + '-'
            response = requests.get(video_url, headers=headers)
            output.write(response.content)
            received_video += len(response.content)
            print('下载进度：%.2f%%' % (received_video / int(video_content.headers['content-length']) * 100))
  
    # 3.4 下载音频开始
    received_audio = 0
    with open(f'{folder}/{video_name}_audio.mp4', 'ab') as output:
        while int(audio_content.headers['content-length']) > received_audio:
            # 视频分片下载
            headers['Range'] = 'bytes=' + str(received_audio) + '-'
            response = requests.get(audio_url, headers=headers)
            output.write(response.content)
            received_audio += len(response.content)
            print('下载进度：%.2f%%' % (received_audio / int(audio_content.headers['content-length']) * 100))
    
    # 3.5 合并视频和音频
    video_data = VideoFileClip(f'{folder}/{video_name}_video.mp4')
    audio_data = AudioFileClip(f'{folder}/{video_name}_audio.mp4')
    final_data = video_data.set_audio(audio_data)
    final_data.write_videofile(f'{folder}/{video_name}.mp4', codec='libx264', audio_codec='aac')

    # 3.6 删除视频和音频
    video_data.close()
    audio_data.close()
    final_data.close()
    os.remove(f'{folder}/{video_name}_video.mp4')
    os.remove(f'{folder}/{video_name}_audio.mp4')
    return title

# B.音频提取和切割
def split_mp3_from_flv(video_path,video_name,audiopath,audioname):
    # 1. 提取音频
    # 将FLV视频文件加载为一个VideoFileClip对象
    video = f"{video_path}/{video_name}.mp4"
    clip = VideoFileClip(video)
    # 提取音频部分
    audio = clip.audio
    # 创建audio/conv文件夹（如果不存在
    os.makedirs(f"{audiopath}", exist_ok=True)
    output_path = f"{audiopath}/{audioname}.mp3"

    # 保存音频并确保文件写入完成
    try:
        audio.write_audiofile(output_path)
        # 等待直到文件被成功创建
        while not os.path.exists(output_path):
            print("正在保存音频文件...")
            time.sleep(1)  # 每秒检查一次文件是否存在
        print(f"音频文件已成功保存到: {output_path}")
    except Exception as e:
        print(f"保存音频文件时发生错误: {e}")
    
    # 2. 切割音频
    # 加载MP3文件
    filename = output_path
    slice_length=45000
    target_folder="slice"
    print(f"Loading audio file: {filename}")
    audio = AudioSegment.from_mp3(filename)

    # 计算分割的数量
    total_slices = len(audio) // slice_length

    # 确保分割目标文件夹存在,且为空
    slice_folder_name = f"{audiopath}/{target_folder}"
    import shutil; shutil.rmtree(slice_folder_name) if os.path.exists(slice_folder_name) else os.makedirs(slice_folder_name)
    os.makedirs(os.path.join(audiopath, target_folder), exist_ok=True)

    for i in range(total_slices):
        # 分割音频
        start = i * slice_length
        end = start + slice_length
        slice = audio[start:end]

        # 构建保存路径
        slice_filename = f"{slice_folder_name}/{i+1}.mp3"

        # 导出分割的音频片段
        slice.export(slice_filename, format="mp3")
        print(f"Slice {i} saved: {slice_filename}")

    # 处理最后一段音频（剩余部分）
    remainder_start = total_slices * slice_length
    if remainder_start < len(audio):  # 如果还有剩余部分
        remainder_audio = audio[remainder_start:]  # 提取剩余部分
        slice_filename = f"{slice_folder_name}/{total_slices + 1}.mp3"

        # 导出剩余音频片段
        remainder_audio.export(slice_filename, format="mp3")
        print(f"Remainder slice saved: {slice_filename}")

    print("Audio splitting complete.")

    return slice_folder_name

# C.cuda可用检查
def is_cuda_available():
    return whisper.torch.cuda.is_available()

# D.模型加载
def load_whisper(model="tiny"):
    global whisper_model
    whisper_model = whisper.load_model(model, device="cuda" if is_cuda_available() else "cpu")
    print("Whisper模型："+model)

# E.音频转文字
def run_analysis(filename, model="tiny", prompt="以下是普通话的句子。", output_folder="bilibili_text", output_filename="chinese",title=""):
    st_t = time.time()
    global whisper_model
    print("正在加载Whisper模型...")
    # 读取列表中的音频文件
    audio_list = os.listdir(f"{filename}")
    audio_list = sorted(audio_list, key=lambda x: int(re.search(r'\d+', x).group()))
    print(audio_list)
    print("加载Whisper模型成功！")
    # 创建outputs文件夹
    os.makedirs(f"{output_folder}", exist_ok=True)
    print("正在转换文本...")

    i = 1
    for fn in audio_list:
        print(f"正在转换第{i}/{len(audio_list)}个音频... {fn}")
        # 识别音频
        result = whisper_model.transcribe(f"{filename}/{fn}", initial_prompt=prompt)
        print("".join([i["text"] for i in result["segments"] if i is not None]))

        with open(f"{output_folder}/{output_filename}.txt", "a", encoding="utf-8") as f:
            if i == 1:
                f.write(f"标题：{title}\n")
            f.write("".join([i["text"] for i in result["segments"] if i is not None]))
            f.write("\n")
        i += 1
    ed_t = time.time()
    elapsed_time = ed_t - st_t  # 计算总耗时
    print(f"所有音频文件转换完成！总耗时: {elapsed_time:.2f}秒")
    print(f"转换结果已保存到: {output_folder}/{output_filename}.txt")
    return f"{output_folder}/{output_filename}.txt"

whisper_model = None

if __name__ == "__main__":
    # 0.加载模型   tiny, base, small, medium, large, turbo
    model_type = 'small'
    load_whisper(model_type)

    # 1.视频下载
    url ='https://www.bilibili.com/video/BV1ZqfXYeEEb/?spm_id_from=333.1387.upload.video_card.click&vd_source=da5da337b290a8d82670403bf1bf31b7'
    v_folder = 'bilibili_video'
    video_name = 'test'
    title = download_video_url(url,v_folder,video_name)

    # 2.音频提取和切割
    audio_folder = "bilibili_audio"
    audio_name = "test"
    slice_folder_name = split_mp3_from_flv(v_folder,video_name,audio_folder,audio_name)
    print(slice_folder_name)

    # 3.语音转文字
    text_folder = "bilibili_text"
    text_name = "chinese"
    run_analysis(slice_folder_name, model=model_type, prompt="以下是普通话的句子。", output_folder=text_folder, output_filename=text_name,title=title)
    print("转换完成！")