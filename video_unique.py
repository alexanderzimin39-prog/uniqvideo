import os
import numpy as np
import cv2
from typing import Callable, List, Optional, Tuple
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, ColorClip, ImageClip
from moviepy.video.fx.all import rotate, resize, speedx
from moviepy.audio.fx.all import volumex


def _fit_within_max_dim(width: int, height: int, max_dim: int) -> Tuple[int, int, float]:
    """Возвращает новую ширину/высоту и коэффициент масштабирования так, чтобы
    максимальная сторона не превышала max_dim. Не апскейлит (scale<=1).
    """
    if max_dim <= 0:
        return width, height, 1.0
    max_side = max(width, height)
    if max_side <= max_dim:
        return width, height, 1.0
    scale = max_dim / float(max_side)
    return int(width * scale), int(height * scale), scale


def _strength_params(strength: str):
    s = (strength or "medium").lower()
    if s == "low":
        return {
            "resize": (0.95, 1.05),
            "speed": (0.98, 1.02),
            "rotate": (-0.5, 0.5),
            "density": (0.4, 0.6),
            "opacity": (0.06, 0.12),
            "bitrate": (0.9, 1.1),
        }
    if s == "high":
        return {
            "resize": (0.6, 1.4),
            "speed": (0.9, 1.1),
            "rotate": (-4.0, 4.0),
            "density": (0.6, 0.8),
            "opacity": (0.15, 0.25),
            "bitrate": (0.7, 1.3),
        }
    # medium (default)
    return {
        "resize": (0.7, 1.3),
        "speed": (0.92, 1.08),
        "rotate": (-2.0, 2.0),
        "density": (0.5, 0.7),
        "opacity": (0.10, 0.18),
        "bitrate": (0.8, 1.2),
    }


def _unique_once(input_path: str, output_dir: str, index: int, strength: str = "medium") -> Tuple[str, int]:
    """
    Выполняет одну итерацию уникализации видео и возвращает путь к результату и использованный битрейт.
    """
    # Загружаем видео и аудио
    video = VideoFileClip(input_path)
    audio = AudioFileClip(input_path) if video.audio is None else video.audio

    # 1. Случайные параметры видео (зависят от силы)
    P = _strength_params(strength)
    resize_factor = np.random.uniform(*P["resize"])  # Разрешение
    speed_factor = np.random.uniform(*P["speed"])    # Скорость
    rotation_angle = np.random.uniform(*P["rotate"]) # Поворот

    video = video.fx(resize, resize_factor)
    video = video.fx(speedx, speed_factor)
    video = video.fx(rotate, rotation_angle)
    audio = audio.fx(volumex, speed_factor)

    # 2. Ограничим итоговое разрешение под слабые планы (без апскейла)
    MAX_DIM = int(os.getenv("MAX_DIM", "720"))
    new_w, new_h, scale_cap = _fit_within_max_dim(video.w, video.h, MAX_DIM)
    if scale_cap < 1.0:
        video = video.fx(resize, scale_cap)

    # 3. Случайный битрейт (±20%)
    try:
        original_bitrate = video.reader.bitrate or 3000
    except Exception:
        original_bitrate = 3000
    bitrate = int(original_bitrate * np.random.uniform(*P["bitrate"]))

    # 4. Цветовой фильтр (генерим после изменения размера)
    color1 = np.array([0, 0, 0, 0])
    color2 = np.array([1, 1, 1, 1])
    random_color = color1 + np.random.rand(4) * (color2 - color1)
    density = np.random.uniform(*P["density"])
    color_filter = ColorClip(
        size=video.size,
        color=(random_color[:3] * 255).astype(int),
        duration=video.duration
    ).set_opacity(density * random_color[3])

    # 5. Создаем уникальный элемент (10-18% прозрачности)
    opacity = np.random.uniform(*P["opacity"])
    element_type = np.random.choice(["rectangle", "noise", "lines", "circle", "gradient"])\
        if min(video.w, video.h) >= 2 else "rectangle"

    if element_type == "rectangle":
        w = np.random.randint(50, max(51, video.w // 2))
        h = np.random.randint(50, max(51, video.h // 2))
        element = ColorClip(
            size=(w, h),
            color=(np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255)),
            duration=video.duration
        ).set_opacity(opacity).set_position((
            np.random.randint(0, max(1, video.w - w)),
            np.random.randint(0, max(1, video.h - h))
        ))

    elif element_type == "noise":
        # Генерируем шум на пониженной сетке, затем масштабируем — экономит память
        down = max(1, int(max(video.w, video.h) / 480))  # примерно до ~480p сетки
        small_w = max(2, video.w // down)
        small_h = max(2, video.h // down)
        noise = (np.random.rand(small_h, small_w, 3) * 255).astype("uint8")
        element = ImageClip(noise, ismask=False, duration=video.duration).resize(video.size)
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
                      np.random.randint(20, max(21, min(video.w, video.h)//4)),
                      (np.random.randint(150, 255),)*3,
                      -1)
        element = ImageClip(circle_img, ismask=False, duration=video.duration)
        element = element.set_opacity(opacity)

    else:  # gradient
        # Строим градиент на уменьшенной сетке и масштабируем
        down = max(1, int(max(video.w, video.h) / 480))
        small_w = max(2, video.w // down)
        small_h = max(2, video.h // down)
        gradient = np.zeros((small_h, small_w, 3), dtype=np.uint8)
        direction = np.random.choice(["horizontal", "vertical", "diagonal"]) if small_w > 1 and small_h > 1 else "horizontal"

        if direction == "horizontal":
            for x in range(small_w):
                intensity = int(255 * (x / max(1, small_w)))
                gradient[:, x] = (intensity, intensity, intensity)
        elif direction == "vertical":
            for y in range(small_h):
                intensity = int(255 * (y / max(1, small_h)))
                gradient[y, :] = (intensity, intensity, intensity)
        else:  # Диагональный
            for x in range(small_w):
                for y in range(small_h):
                    intensity = int(255 * ((x + y) / max(1, (small_w + small_h))))
                    gradient[y, x] = (intensity, intensity, intensity)

        element = ImageClip(gradient, ismask=False, duration=video.duration).resize(video.size)
        element = element.set_opacity(opacity * 0.5)

    # Собираем композицию
    final_video = CompositeVideoClip([video, color_filter, element]).set_audio(audio)

    # Сохранение с уникальным именем
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_name = f"{base_name}_{index}.mp4"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_name)

    # Параметры кодека из окружения для экономии ресурсов
    VIDEO_THREADS = int(os.getenv("VIDEO_THREADS", "1"))
    FFMPEG_PRESET = os.getenv("FFMPEG_PRESET", "veryfast")

    final_video.write_videofile(
        output_path,
        codec="libx264",
        fps=24,
        audio_codec="aac",
        bitrate=f"{bitrate}k",
        threads=VIDEO_THREADS,
        preset=FFMPEG_PRESET
    )

    return output_path, bitrate


def unique_video(
    input_path: str,
    copies: int = 1,
    output_dir: Optional[str] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    strength: str = "medium",
) -> List[str]:
    """
    Генерирует несколько уникальных копий видео.

    Args:
        input_path: путь к исходному видео
        copies: количество копий
        output_dir: каталог для сохранения (по умолчанию рядом с оригиналом, в подпапке "unique")
        progress_cb: callback(progress_index, output_path) — для уведомления о прогрессе

    Returns:
        Список путей к созданным файлам
    """
    if output_dir is None:
        base_dir = os.path.dirname(os.path.abspath(input_path))
        output_dir = os.path.join(base_dir, "unique")

    outputs: List[str] = []
    for i in range(1, copies + 1):
        # Дополнительная энтропия в генераторе
        np.random.seed(None)
        out_path, _ = _unique_once(input_path, output_dir, i, strength=strength)
        outputs.append(out_path)
        if progress_cb:
            try:
                progress_cb(i, out_path)
            except Exception:
                pass
    return outputs
