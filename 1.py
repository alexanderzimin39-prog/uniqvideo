import numpy as np
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, ColorClip, ImageClip
from moviepy.video.fx.all import rotate, resize, speedx
from moviepy.audio.fx.all import volumex
import os
import cv2

def process_video(input_path, output_suffix):
    # Загружаем видео и аудио
    video = VideoFileClip(input_path)
    audio = AudioFileClip(input_path) if video.audio is None else video.audio

    # 1. Случайный цветовой фильтр (каждый раз разный)
    color1 = np.array([0, 0, 0, 0])
    color2 = np.array([1, 1, 1, 1])
    random_color = color1 + np.random.rand(4) * (color2 - color1)
    density = np.random.uniform(0.5, 0.7)  # Плотность 50-70%
    
    color_filter = ColorClip(
        size=video.size,
        color=(random_color[:3] * 255).astype(int),
        duration=video.duration
    ).set_opacity(density * random_color[3])

    # 2. Случайные параметры видео (уникальные для каждого файла)
    resize_factor = np.random.uniform(0.7, 1.3)  # Разрешение 70-130%
    speed_factor = np.random.uniform(0.92, 1.08)  # Скорость ±8%
    rotation_angle = np.random.uniform(-2, 2)     # Поворот ±2°
    
    video = video.fx(resize, resize_factor)
    video = video.fx(speedx, speed_factor)
    video = video.fx(rotate, rotation_angle)
    audio = audio.fx(volumex, speed_factor)

    # 3. Случайный битрейт (±20%)
    try:
        original_bitrate = video.reader.bitrate or 3000
    except:
        original_bitrate = 3000
    bitrate = int(original_bitrate * np.random.uniform(0.8, 1.2))

    # 4. Создаем уникальный элемент (10-18% прозрачности)
    opacity = np.random.uniform(0.1, 0.18)
    element_type = np.random.choice(["rectangle", "noise", "lines", "circle", "gradient"])
    
    if element_type == "rectangle":
        w = np.random.randint(50, video.w // 2)
        h = np.random.randint(50, video.h // 2)
        element = ColorClip(
            size=(w, h),
            color=(np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255)),
            duration=video.duration
        ).set_opacity(opacity).set_position((
            np.random.randint(0, video.w - w),
            np.random.randint(0, video.h - h)
        ))

    elif element_type == "noise":
        noise = np.random.rand(video.h, video.w, 3) * 255
        element = ImageClip(noise.astype('uint8'), ismask=False, duration=video.duration)
        element = element.set_opacity(opacity)

    elif element_type == "lines":  # Уникальные линии
        line_img = np.zeros((video.h, video.w, 3), dtype=np.uint8)
        for _ in range(np.random.randint(3, 8)):
            y = np.random.randint(0, video.h)
            cv2.line(line_img, 
                    (0, y), 
                    (video.w, y),
                    (np.random.randint(200, 255),)*3,
                    np.random.randint(1, 5))
        element = ImageClip(line_img, ismask=False, duration=video.duration)
        element = element.set_opacity(opacity * 0.7)

    elif element_type == "circle":  # Уникальные круги
        circle_img = np.zeros((video.h, video.w, 3), dtype=np.uint8)
        for _ in range(np.random.randint(2, 5)):
            cv2.circle(circle_img,
                      (np.random.randint(0, video.w), np.random.randint(0, video.h)),
                      np.random.randint(20, min(video.w, video.h)//4),
                      (np.random.randint(150, 255),)*3,
                      -1)
        element = ImageClip(circle_img, ismask=False, duration=video.duration)
        element = element.set_opacity(opacity)

    elif element_type == "gradient":  # Уникальный градиент
        gradient = np.zeros((video.h, video.w, 3), dtype=np.uint8)
        direction = np.random.choice(["horizontal", "vertical", "diagonal"])
        
        if direction == "horizontal":
            for x in range(video.w):
                intensity = int(255 * (x / video.w))
                gradient[:, x] = (intensity, intensity, intensity)
        elif direction == "vertical":
            for y in range(video.h):
                intensity = int(255 * (y / video.h))
                gradient[y, :] = (intensity, intensity, intensity)
        else:  # Диагональный
            for x in range(video.w):
                for y in range(video.h):
                    intensity = int(255 * ((x + y) / (video.w + video.h)))
                    gradient[y, x] = (intensity, intensity, intensity)
        
        element = ImageClip(gradient, ismask=False, duration=video.duration)
        element = element.set_opacity(opacity * 0.5)

    # Собираем композицию
    final_video = CompositeVideoClip([video, color_filter, element]).set_audio(audio)

    # Сохранение с уникальным именем
    base_name = os.path.splitext(input_path)[0]
    output_path = f"{base_name}_{output_suffix}.mp4"
    
    final_video.write_videofile(
        output_path,
        codec="libx264",
        fps=24,
        audio_codec="aac",
        bitrate=f"{bitrate}k",
        threads=4,
        preset='fast'
    )
    print(f"Создан уникальный файл: {output_path}")

if __name__ == "__main__":
    input_file = input("Введите путь к видеофайлу: ")
    
    while True:
        try:
            num_files = int(input("Сколько файлов создать (1-100)? "))
            if 1 <= num_files <= 100:
                break
            print("Пожалуйста, введите число от 1 до 100")
        except ValueError:
            print("Пожалуйста, введите число")

    for i in range(1, num_files + 1):
        process_video(input_file, i)