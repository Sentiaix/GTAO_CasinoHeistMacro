import os
import cv2
import numpy as np
import time
import pydirectinput
import pyautogui
from PIL import ImageGrab
import keyboard
import winsound
import sys
import configparser
from functools import lru_cache

# -- [설정] 사용자 요청 config default format 반영 --
DEFAULT_CONFIG = """[SETTINGS]
# 인식 정확도 (낮을수록 쉽게 인식, 높을수록 까다롭게 인식)
# big  >> 우측 큰 지문 인식률 설정
# part >> 좌측 8개의 지문 조각 인식률 설정
# trap >> 4 * 4 = 16개의 올바른 지문 조각에 절대 포함되지 않는 지문 조각의 탐지율
# 기본값: 0.38, 0.33, 0.73
threshold_big = 0.38
threshold_part = 0.33
threshold_trap = 0.73

# 화면 보정 (지문이 좌우로 밀려 보일 때만 조정)
# 좌(-), 우(+), (기본값: 0)
wqhd_offset_x = 0

[HOTKEYS]
# 기본값: F4 ~ F8
exit = F4
start = F5
restart = F6
check = F7
debug = F8
"""

# -- 전역 변수 초기화 --
SET, HK = None, None
T_BIG, T_PART, T_TRAP = 0.38, 0.33, 0.73
WQHD_OFFSET_X = 0
RATIO_W, RATIO_H, IMG_SCALE = 1.0, 1.0, 1.0
BIG_REGION_BBOX, X_COORDS, Y_BASES, PART_SIZE_PX = None, None, None, None

FINGER_MAP = {f'big_finger{i}.png': [f'part_{i}_{j}.png' for j in range(1, 5)] for i in range(1, 5)}
BLACKLIST_MAP = {f'big_finger{i}.png': f'b{i}.png' for i in range(1, 5)}
PROCESSED_TEMPLATES = {}

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def preload_all_templates():
    global PROCESSED_TEMPLATES
    PROCESSED_TEMPLATES.clear()
    all_images = set()
    for big_img, parts in FINGER_MAP.items():
        all_images.add(big_img); all_images.update(parts)
    for trap_img in BLACKLIST_MAP.values():
        all_images.add(trap_img)

    for filename in all_images:
        path = resource_path(filename)
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            PROCESSED_TEMPLATES[filename] = img

@lru_cache(maxsize=128)
def get_scaled_template(filename, scale_factor):
    if filename not in PROCESSED_TEMPLATES: return None
    template = PROCESSED_TEMPLATES[filename]
    new_size = (int(template.shape[1] * scale_factor), int(template.shape[0] * scale_factor))
    resized = cv2.resize(template, new_size, interpolation=cv2.INTER_LANCZOS4)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(resized)
    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
    binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 5)
    return binary

def fast_preprocess_screenshot(img_np):
    img_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img_gray = clahe.apply(img_gray)
    img_blur = cv2.GaussianBlur(img_gray, (3, 3), 0)
    img_bin = cv2.adaptiveThreshold(img_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 5)
    return img_bin

def get_rel_pos_bbox(x, y, w, h):
    return (int(x * RATIO_W) + WQHD_OFFSET_X, int(y * RATIO_H), int((x + w) * RATIO_W) + WQHD_OFFSET_X, int((y + h) * RATIO_H))

def load_config_logic():
    global SET, HK, T_BIG, T_PART, T_TRAP, WQHD_OFFSET_X
    global RATIO_W, RATIO_H, IMG_SCALE, BIG_REGION_BBOX, X_COORDS, Y_BASES, PART_SIZE_PX

    config = configparser.ConfigParser()
    config_path = "config.ini"
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f: f.write(DEFAULT_CONFIG)
        config.read_string(DEFAULT_CONFIG)
    else:
        config.read(config_path, encoding='utf-8')

    SET = config['SETTINGS'] if 'SETTINGS' in config else {}
    HK = config['HOTKEYS'] if 'HOTKEYS' in config else {}
    
    T_BIG = float(config.get('SETTINGS', 'threshold_big', fallback=0.38))
    T_PART = float(config.get('SETTINGS', 'threshold_part', fallback=0.33))
    T_TRAP = float(config.get('SETTINGS', 'threshold_trap', fallback=0.73))
    WQHD_OFFSET_X = int(config.get('SETTINGS', 'wqhd_offset_x', fallback=0))

    SCREEN_W, SCREEN_H = pyautogui.size()
    RATIO_W, RATIO_H = SCREEN_W / 1920, SCREEN_H / 1080
    aspect_ratio = SCREEN_W / SCREEN_H
    IMG_SCALE = RATIO_H if aspect_ratio > 1.8 else min(RATIO_W, RATIO_H)

    BIG_REGION_BBOX = get_rel_pos_bbox(960, 160, 360, 520)
    X_COORDS = [int(473 * RATIO_W) + WQHD_OFFSET_X, int(617 * RATIO_W) + WQHD_OFFSET_X]
    Y_BASES = [int(269 * RATIO_H), int(412 * RATIO_H), int(555 * RATIO_H), int(698 * RATIO_H)]
    PART_SIZE_PX = int(122 * IMG_SCALE)

    preload_all_templates()
    get_scaled_template.cache_clear()

def setup_hotkeys():
    config = configparser.ConfigParser()
    config.read("config.ini", encoding='utf-8')
    def k_get(name, default): return config.get('HOTKEYS', name, fallback=default).strip().lower()

    keyboard.add_hotkey(k_get('exit', 'f4'), exit_program)
    keyboard.add_hotkey(k_get('start', 'f5'), run_hack)
    keyboard.add_hotkey(k_get('restart', 'f6'), reload_system)
    keyboard.add_hotkey(k_get('check', 'f7'), lambda: winsound.Beep(1000, 100))
    keyboard.add_hotkey(k_get('debug', 'f8'), debug_mode)

def exit_program():
    winsound.Beep(400, 200)
    os._exit(0)

def reload_system():
    winsound.Beep(800, 150)
    keyboard.unhook_all()
    load_config_logic()
    setup_hotkeys()
    os.system('cls' if os.name == 'nt' else 'clear')
    display_banner_logic()
    winsound.Beep(1200, 150)

def display_banner_logic():
    config = configparser.ConfigParser()
    config.read("config.ini", encoding='utf-8')
    def k_up(name, default): return config.get('HOTKEYS', name, fallback=default).strip().upper()
    
    # 좌우 대칭과 모든 키 가시성을 확보한 레이아웃
    banner = f"""
============================================================
                 GTA 5 Casino Heist Macro                  
       Detected: {pyautogui.size()[0]} x {pyautogui.size()[1]} (Scale: {IMG_SCALE:.2f})        
------------------------------------------------------------
   종료:{k_up('exit', 'F4'):<3} | 시작:{k_up('start', 'F5'):<3} | 재시작:{k_up('restart', 'F6'):<3} | 체크:{k_up('check', 'F7'):<3} | 디버그:{k_up('debug', 'F8'):<3}
------------------------------------------------------------
 인식이 안 될 경우 {k_up('debug', 'F8')}를 눌러 매칭 스코어를 확인하거나      
 config.ini 파일을 참고하여 인식률을 조정해보세요.           
 이 프로그램은 1920 x 1080 해상도에 맞춰 제작되었습니다.     
------------------------------------------------------------
              * 창 모드 또는 전체 창 모드 권장              
------------------------------------------------------------
       빌드 파일 및 소스 코드, 자세한 설명서는 아래 참고      
       https://github.com/Sentiaix/GTAO5_fingerMacro       
============================================================
"""
    print(banner, flush=True)

def debug_mode():
    print("\n[DEBUG] 매칭 테스트 시작 (debug.png 저장됨)")
    try:
        ImageGrab.grab(bbox=BIG_REGION_BBOX).save("debug.png")
        img_bin = fast_preprocess_screenshot(np.array(ImageGrab.grab(bbox=BIG_REGION_BBOX)))
        for big_img in FINGER_MAP.keys():
            score = 0.0
            for s in [0.98, 1.0, 1.02]:
                temp = get_scaled_template(big_img, IMG_SCALE * s)
                if temp is not None:
                    res = cv2.matchTemplate(img_bin, temp, cv2.TM_CCOEFF_NORMED)
                    score = max(score, cv2.minMaxLoc(res)[1])
            print(f" > {big_img}: {score:.3f} (기준: {T_BIG})")
    except Exception as e: print(f"[!] 디버그 실패: {e}")

def run_hack():
    img_big_bin = fast_preprocess_screenshot(np.array(ImageGrab.grab(bbox=BIG_REGION_BBOX)))
    selected_key, best_big_score = None, 0.0
    for big_img in FINGER_MAP.keys():
        score = 0.0
        for s in [0.98, 1.0, 1.02]:
            temp = get_scaled_template(big_img, IMG_SCALE * s)
            if temp is not None:
                res = cv2.matchTemplate(img_big_bin, temp, cv2.TM_CCOEFF_NORMED)
                score = max(score, cv2.minMaxLoc(res)[1])
        if score > best_big_score: best_big_score, selected_key = score, big_img
    
    if not selected_key or best_big_score < T_BIG: return

    answer_parts, trap_img = FINGER_MAP[selected_key], BLACKLIST_MAP[selected_key]
    trap_temp = get_scaled_template(trap_img, IMG_SCALE)
    
    final_results = []
    for cell_idx, (y_base, x_coord) in enumerate([(y, x) for y in Y_BASES for x in X_COORDS], 1):
        roi_bbox = (x_coord, y_base, x_coord + PART_SIZE_PX, y_base + PART_SIZE_PX)
        roi_bin = fast_preprocess_screenshot(np.array(ImageGrab.grab(bbox=roi_bbox)))
        if trap_temp is not None:
            if cv2.minMaxLoc(cv2.matchTemplate(roi_bin, trap_temp, cv2.TM_CCOEFF_NORMED))[1] >= T_TRAP:
                final_results.append({'id': cell_idx, 'score': -1.0}); continue
        p_score = 0.0
        for p in answer_parts:
            for s in [0.98, 1.0, 1.02]:
                t = get_scaled_template(p, IMG_SCALE * s)
                if t is not None:
                    p_score = max(p_score, cv2.minMaxLoc(cv2.matchTemplate(roi_bin, t, cv2.TM_CCOEFF_NORMED))[1])
        final_results.append({'id': cell_idx, 'score': p_score})

    top_4 = sorted(final_results, key=lambda x: x['score'], reverse=True)[:4]
    target_ids = {x['id'] for x in top_4}
    for i in range(1, 9):
        if i in target_ids: pydirectinput.press('enter')
        if i < 8: pydirectinput.press('right'); time.sleep(0.01)
    time.sleep(0.1); pydirectinput.press('tab')

if __name__ == "__main__":
    pydirectinput.PAUSE = 0.01
    load_config_logic()
    setup_hotkeys()
    winsound.Beep(1000, 100); time.sleep(0.1); winsound.Beep(1000, 100)
    os.system('cls' if os.name == 'nt' else 'clear')
    display_banner_logic()
    while True:
        time.sleep(0.01)
