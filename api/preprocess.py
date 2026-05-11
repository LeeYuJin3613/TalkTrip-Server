import re

def clean_raw_text(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.strip()
    text = re.sub(r'[ \t]+', ' ', text)
    return text


def is_system_message(message: str) -> bool:
    system_keywords = [
        '저장한 날짜',
        '님이 들어왔습니다',
        '님이 나갔습니다',
        '삭제된 메시지입니다',
        '사진',
        '이모티콘',
        '동영상',
        '파일:'
    ]
    return any(keyword in message for keyword in system_keywords)


def convert_kakao_time(period: str, hour: int, minute: int) -> str:
    if period == '오전':
        if hour == 12:
            hour = 0
    elif period == '오후':
        if hour != 12:
            hour += 12
    return f'{hour:02d}:{minute:02d}'


def parse_kakao_chat(raw_text: str):
    text = clean_raw_text(raw_text)
    lines = text.split('\n')

    date_pattern = re.compile(r'(\d{4})년 (\d{1,2})월 (\d{1,2})일')
    message_pattern = re.compile(
        r'^(오전|오후) (\d{1,2}):(\d{2}), (.+?) : (.*)$'
    )

    current_date = None
    messages = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        date_match = date_pattern.search(line)
        if date_match:
            year, month, day = map(int, date_match.groups())
            current_date = f'{year:04d}-{month:02d}-{day:02d}'
            continue

        msg_match = message_pattern.match(line)
        if msg_match:
            period, hour, minute, speaker, message = msg_match.groups()
            time_24 = convert_kakao_time(period, int(hour), int(minute))

            if not is_system_message(message):
                messages.append({
                    'date': current_date,
                    'time': time_24,
                    'speaker': speaker.strip(),
                    'message': message.strip(),
                })
        else:
            if messages:
                messages[-1]['message'] += '\n' + line

    for idx, msg in enumerate(messages, start=1):
        msg['id'] = idx

    return messages