import os
import cv2
import numpy as np
import time
import pydirectinput
import pyautogui
import keyboard
import winsound
import sys

'''
================================================================================
[ GTA5 Cayo Perico Fingerprint Hacker - Optimized Version ]

1. 주요 기능:
   - F4: 프로그램 즉시 종료 (EXIT)
   - F5: 지문 분석 및 해킹 자동 실행 (START)
   - F7: 시스템 상태 확인 부저음 (CHECK)

2. 최적화 및 수정 사항:
   - [입력 최적화] pydirectinput.PAUSE를 0.01로 단축하여 키 입력 속도 극대화.
   - [딜레이 제어] 각 파츠 선택 사이 이동 대기 0.02초, 최종 Tab 입력 전 0.1초 대기 적용.
   - [정밀도 향상] Gaussian Blur와 Adaptive Threshold를 결합한 고정밀 지문 패턴 분석.
   - [사용성 개선] 
     * 프로그램 실행 시 시작 알림음 (0.1초 간격 2회 비프음).
     * F7 키 입력 시 시스템 활성화 확인용 단일 비프음.
     * 모든 디버그 로그 및 실행 로그 제거 (Clean Console UI).
   - [배포 최적화] PyInstaller 빌드 시 이미지 리소스 포함을 위한 resource_path 로직 적용.

3. 실행 주의사항:
   - 게임 엔진 내 키 입력 전달을 위해 반드시 '관리자 권한'으로 실행해야 함.
   - 1920x1080 해상도 및 표준 UI 크기에 최적화됨.
================================================================================
'''

# 1. 리소스 경로 해결 함수
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 2. 초기 설정
pydirectinput.PAUSE = 0.01

FINGER_MAP = {
    'big_finger1.png': [f'part_1_{i}.png' for i in range(1, 5)],
    'big_finger2.png': [f'part_2_{i}.png' for i in range(1, 5)],
    'big_finger3.png': [f'part_3_{i}.png' for i in range(1, 5)],
    'big_finger4.png': [f'part_4_1.png', 'part_4_2.png', 'part_4_3.png', 'part_4_4.png']
}

BLACKLIST_MAP = {
    'big_finger1.png': 'b1.png',
    'big_finger2.png': 'b2.png',
    'big_finger3.png': 'b3.png',
    'big_finger4.png': 'b4.png'
}

X_COORDS = [473, 617]
Y_BASES = [269, 412, 555, 698]
Y_OFFSETS = [0, 1, 2, 3]

def get_precision_score(target_filename, region):
    """ 기존 가우시안 블러 + 적응형 이진화 방식 """
    try:
        left, top, w, h = region
        screenshot = pyautogui.screenshot(region=(left, top, w, h))
        img_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
        
        path = resource_path(target_filename)
        template_gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if template_gray is None: return 0.0

        # 고정밀 가우시안 처리
        img_blur = cv2.GaussianBlur(img_gray, (3, 3), 0)
        temp_blur = cv2.GaussianBlur(template_gray, (3, 3), 0)

        # 적응형 이진화
        img_bin = cv2.adaptiveThreshold(img_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                        cv2.THRESH_BINARY, 11, 2)
        temp_bin = cv2.adaptiveThreshold(temp_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY, 11, 2)

        res = cv2.matchTemplate(img_bin, temp_bin, cv2.TM_CCOEFF_NORMED)
        return cv2.minMaxLoc(res)[1]
    except:
        return 0.0

# --- 기능 함수 ---

def exit_program():
    """ F4: 즉시 종료 """
    winsound.Beep(500, 300)
    os._exit(0)

def run_hack():
    """ F5: 해킹 실행 """
    # 1. 중앙 지문 인식
    big_region = (960, 160, 360, 520)
    selected_key = None
    best_big_score = 0.0
    
    for big_img in FINGER_MAP.keys():
        score = get_precision_score(big_img, big_region)
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
        y = Y_BASES[row] + Y_OFFSETS[row]
        for x in X_COORDS:
            region = (x, y, 122, 122)
            # 함정 확인 (정밀도 0.92 기준)
            if get_precision_score(trap_img, region) >= 0.92:
                score = -2.0
            else:
                score = max([get_precision_score(p, region) for p in answer_parts])
            
            final_results.append({'id': cell_idx, 'score': score})
            cell_idx += 1

    # 3. 입력 로직
    top_4 = sorted(final_results, key=lambda x: x['score'], reverse=True)[:4]
    target_ids = {item['id'] for item in top_4}
    
    for i in range(1, 9):
        if i in target_ids:
            pydirectinput.press('enter')
        if i < 8:
            pydirectinput.press('right')
            time.sleep(0.02)
            
    time.sleep(0.1) # 마지막 Tab 전 0.1초 대기
    pydirectinput.press('tab')

def play_buzzer():
    """ F7: 상태 확인 (삐- 1번) """
    winsound.Beep(1000, 100)

# --- 메인 루틴 ---

if __name__ == "__main__":
    # 실행 시 시작음 (삐-삐-)
    winsound.Beep(1000, 100)
    time.sleep(0.1)
    winsound.Beep(1000, 100)

    # 안내 표 (최소한의 안내만 제공)
    print("========================================")
    print(" F4: EXIT | F5: START | F7: CHECK ")
    print(" 사용방법: 지문이 보이면 F5를 누른 후 대기.")
    print(" 만약 실행되지 않는다면 관리자 권한으로 재실행")
    print("========================================")

    keyboard.add_hotkey('f4', exit_program)
    keyboard.add_hotkey('f5', run_hack)
    keyboard.add_hotkey('f7', play_buzzer)

    while True:
        time.sleep(0.01)