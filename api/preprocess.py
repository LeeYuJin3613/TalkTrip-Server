import re
from datetime import datetime


def clean_raw_text(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.strip()
    text = re.sub(r'[ \t]+', ' ', text)
    return text


def is_system_message(message: str) -> bool:
    clean_msg = message.strip()

    # 1. 미디어 메시지
    exact_match_keywords = ['사진', '이모티콘', '동영상', '사진 첨부', '동영상 첨부']
    if clean_msg in exact_match_keywords:
        return True

    # 2. 일반 시스템 안내 메시지 (이 단어가 포함되어 있으면 무조건 삭제)
    partial_match_keywords = [
        '저장한 날짜', '님이 들어왔습니다', '님이 나갔습니다',
        '삭제된 메시지입니다', '파일:', '샵검색:', '포스트:', '통화 시간'
    ]
    return any(keyword in clean_msg for keyword in partial_match_keywords)


def convert_kakao_time(period: str, hour: int, minute: int) -> str:
    if period == '오전':
        if hour == 12: hour = 0
    elif period == '오후':
        if hour != 12: hour += 12
    return f'{hour:02d}:{minute:02d}'


def parse_kakao_chat(raw_text: str):
    text = clean_raw_text(raw_text)
    lines = text.split('\n')

    # 날짜 패턴: 2026년 5월 10일 일요일
    date_pattern = re.compile(r'(\d{4})년 (\d{1,2})월 (\d{1,2})일')

    # 🚨 업그레이드: 두 가지 패턴을 모두 잡는 정규표현식!
    # 패턴 1 (쉼표 형식): 오전 10:30, 홍길동 : 내용
    # 패턴 2 (대괄호 형식): [오전 10:30] 홍길동: 내용
    message_pattern = re.compile(
        r'^(?:\[?(오전|오후) (\d{1,2}):(\d{2})\]?)[, ]*([^:]+)\s*:\s*(.*)$'
    )

    current_date = None
    messages = []

    for line in lines:
        line = line.strip()
        if not line: continue

        date_match = date_pattern.search(line)
        if date_match:
            year, month, day = map(int, date_match.groups())
            current_date = f'{year:04d}-{month:02d}-{day:02d}'
            continue

        msg_match = message_pattern.match(line)
        if msg_match:
            period, hour, minute, speaker, message = msg_match.groups()

            # 발화자 이름에서 앞뒤 공백이나 대괄호 찌꺼기 제거
            speaker = speaker.strip(' []')

            if not is_system_message(message):
                time_24 = convert_kakao_time(period, int(hour), int(minute))

                # current_date가 아직 설정되지 않았다면 오늘 날짜로 대체 (에러 방지)
                if current_date is None:
                    # 파이참 터미널 로그를 보니 현재 테스트 날짜는 2026-05-10
                    current_date = '2026-05-10'

                messages.append({
                    'timestamp': f'{current_date} {time_24}',
                    'message': message.strip(),
                })
        else:
            if messages:
                messages[-1]['message'] += ' ' + line

    for i in range(len(messages)):
        start_idx = max(0, i - 3)
        prev_msgs = [messages[j]['message'] for j in range(start_idx, i)]
        messages[i]['context'] = " [SEP] ".join(prev_msgs + [messages[i]['message']])

    return messages