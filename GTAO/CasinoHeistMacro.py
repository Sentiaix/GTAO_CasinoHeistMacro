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
import subprocess

# -- memo -- #
#
# argument랑 LLM해서 하는게 더 빠르고 정확할 것 같은데
# 처음이라 많은 시도를 하기도 힘들고 이미 많이 짜버림
#
# mss 사용하려 했으나 이미지 인식에 있어선 가우시안 블러가 더 정확함.
# 다양한 해상도에도 적용하기 위해 이미지의 크기 resize,
# 동적 해상도에 따른 비율계산 로직 추가
# F6키를 눌렀을때 프로그램을 재시작 하는 기능 추가. (큰 의미 없어보임)
# 알 수 없는 이유로 F6 눌렀을때 png파일을 찾는 로직이 꼬임.
# 아마도 exe에서 호출할때 MEIPASS나 os.execl이 오류내는 것 같음


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# 1. 전역 설정 및 해상도 비율 계산
pydirectinput.PAUSE = 0.01

# 현재 해상도 감지
SCREEN_W, SCREEN_H = pyautogui.size()
# 1920x1080(기준) 대비 현재 해상도 비율
RATIO_W = SCREEN_W / 1920
RATIO_H = SCREEN_H / 1080
# 이미지 리사이징 배율 (가로세로 비율 중 작은 쪽을 기준으로 왜곡 방지)
IMG_SCALE = min(RATIO_W, RATIO_H)

FINGER_MAP = {f'big_finger{i}.png': [f'part_{i}_{j}.png' for j in range(1, 5)] for i in range(1, 5)}
BLACKLIST_MAP = {f'big_finger{i}.png': f'b{i}.png' for i in range(1, 5)}

# 2. 유동적 좌표 계산 함수 (PIL bbox 형식: left, top, right, bottom)
def get_rel_pos_bbox(x, y, w, h):
    return (
        int(x * RATIO_W), 
        int(y * RATIO_H), 
        int((x + w) * RATIO_W), 
        int((y + h) * RATIO_H)
    )

# 동적 영역 설정
BIG_REGION_BBOX = get_rel_pos_bbox(960, 160, 360, 520)
X_COORDS = [int(473 * RATIO_W), int(617 * RATIO_W)]
Y_BASES = [int(269 * RATIO_H), int(412 * RATIO_H), int(555 * RATIO_H), int(698 * RATIO_H)]
PART_SIZE_PX = int(122 * IMG_SCALE)

# --- [안정적인 분석 함수] PIL 기반 ---
def get_precision_score(target_filename, region_bbox):
    try:
        # ImageGrab 방식
        screenshot = ImageGrab.grab(bbox=region_bbox)
        img_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
        
        path = resource_path(target_filename)
        template_gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if template_gray is None: return 0.0

        # [리사이징] 현재 해상도에 맞춰 지문 템플릿 크기 조절
        if IMG_SCALE != 1.0:
            new_size = (int(template_gray.shape[1] * IMG_SCALE), int(template_gray.shape[0] * IMG_SCALE))
            template_gray = cv2.resize(template_gray, new_size, interpolation=cv2.INTER_LANCZOS4)

        # 가우시안 블러 및 이진화 (기존 방식 유지)
        img_blur = cv2.GaussianBlur(img_gray, (3, 3), 0)
        temp_blur = cv2.GaussianBlur(template_gray, (3, 3), 0)

        img_bin = cv2.adaptiveThreshold(img_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                        cv2.THRESH_BINARY, 11, 2)
        temp_bin = cv2.adaptiveThreshold(temp_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY, 11, 2)

        res = cv2.matchTemplate(img_bin, temp_bin, cv2.TM_CCOEFF_NORMED)
        return cv2.minMaxLoc(res)[1]
    except Exception:
        return 0.0

# F4 키 할당 함수
def exit_program():
    winsound.Beep(500, 300)
    os._exit(0)

# F6 키 할당 함수
def restart_program():
    """프로그램 재시작"""
    winsound.Beep(800, 100)
    winsound.Beep(1200, 100)
    print("Restarting program...")

    # 현재 실행 중인 파일의 경로 (EXE 또는 .py)
    executable = sys.executable
    args = sys.argv

    # 새로운 프로세스를 독립적으로 실행
    subprocess.Popen([executable] + args, shell=True)
    
    # 현재 프로세스는 즉시 종료 (임시 폴더 꼬임 방지)
    os._exit(0)

def run_hack():
    selected_key = None
    best_big_score = 0.0
    
    # 1. 중앙 지문 인식
    for big_img in FINGER_MAP.keys():
        score = get_precision_score(big_img, BIG_REGION_BBOX)
        if score > best_big_score:
            best_big_score = score
            selected_key = big_img
            
    if not selected_key or best_big_score < 0.4:
        return

    # 2. 8개 파츠 분석
    answer_parts = FINGER_MAP[selected_key]
    trap_img = BLACKLIST_MAP[selected_key]
    final_results = []
    cell_idx = 1
    
    for row in range(4):
        y = Y_BASES[row]
        for x in X_COORDS:
            # 파츠별 bbox 설정
            region = (x, y, x + PART_SIZE_PX, y + PART_SIZE_PX)
            if get_precision_score(trap_img, region) >= 0.80:
                score = -2.0
            else:
                score = max([get_precision_score(p, region) for p in answer_parts])
            
            final_results.append({'id': cell_idx, 'score': score})
            cell_idx += 1

    # 3. 입력 실행
    top_4 = sorted(final_results, key=lambda x: x['score'], reverse=True)[:4]
    target_ids = {item['id'] for item in top_4}
    
    for i in range(1, 9):
        if i in target_ids:
            pydirectinput.press('enter')
        if i < 8:
            pydirectinput.press('right')
            time.sleep(0.02)
            
    time.sleep(0.1)
    pydirectinput.press('tab')

def play_buzzer():
    winsound.Beep(1000, 100)

if __name__ == "__main__":
    winsound.Beep(1000, 100)
    time.sleep(0.1)
    winsound.Beep(1000, 100)

    print("==================================================")
    print("            GTA 5 Casino Heist Macro ")
    print(f" 감지된 해상도: {SCREEN_W} x {SCREEN_H} (비율: {IMG_SCALE:.2f})")
    print("--------------------------------------------------")
    print(" F4: 종료 | F5: 실행 | F6: 재시작 | F7: 상태 확인 ")
    print("--------------------------------------------------")
    print(" 정확도가 낮다면, 1920 x 1080 해상도로 바꾼 뒤 ")
    print(" 게임 창을 가장 좌상단에 위치시켜 사용해보세요. ")
    print(" * 창 모드 또는 전체 창 모드를 추천합니다. ")
    print("--------------------------------------------------")
    print(" 빌드 및 원본 파일, 자세한 설명서는 아래를 참고")
    print(" https://github.com/Sentiaix/GTAO5_fingerMacro")
    print("==================================================")

    keyboard.add_hotkey('f4', exit_program)
    keyboard.add_hotkey('f5', run_hack)
    keyboard.add_hotkey('f6', restart_program)
    keyboard.add_hotkey('f7', play_buzzer)

    while True:
        time.sleep(0.01)
