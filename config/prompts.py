import re
from typing import Optional

PROMPT_PART1 = """
Bạn là chuyên gia viết bài SEO. Viết PHẦN 1 của bài blog với tiêu đề: "{title}"

TỪ KHÓA SEO CHÍNH: "{keyword}"
CÔNG TY: THANG MÁY KENZO VIỆT NAM

CHỈ VIẾT PHẦN 1 (khoảng 800 TỪ), bao gồm:

1. ĐOạN MỞ ĐẦU (200 từ):
<p>Viết đoạn mở đầu hấp dẫn giới thiệu về <strong>{keyword}</strong>. Giải thích tại sao đây là chủ đề quan trọng, nêu bật lợi ích và giá trị. Đề cập đến THANG MÁY KENZO VIỆT NAM như đơn vị uy tín trong lĩnh vực này.</p>

2. <h2>Tổng quan về {keyword}</h2> (200 từ):
<p>Viết đoạn chi tiết về khái niệm, định nghĩa, tầm quan trọng của <strong>{keyword}</strong>. Mô tả các đặc điểm chính, ứng dụng phổ biến.</p>

3. <h2>Lợi ích nổi bật của {keyword}</h2> (200 từ):
<p>Giải thích chi tiết các lợi ích:</p>
<ul>
<li>An toàn và tiện nghi</li>
<li>Tiết kiệm không gian</li>
<li>Tăng giá trị bất động sản</li>
<li>Phù hợp nhiều đối tượng</li>
</ul>
<p>Mô tả cụ thể từng lợi ích với <strong>{keyword}</strong>.</p>

4. <h2>Báo giá {keyword} mới nhất năm 2025</h2> (200 từ):
<p>Cung cấp thông tin chi tiết về mức giá, các yếu tố ảnh hưởng đến giá, so sánh giá của các loại khác nhau.</p>

QUY TẮC:
- CHỈ DÙNG HTML (<h2>, <p>, <ul>, <li>, <strong>)
- KHÔNG dùng Markdown (##, **)
- Từ khóa "{keyword}" phải in đậm: <strong>{keyword}</strong>
- Mỗi phần PHẢI có ít nhất 200 từ

Xuất ra HTML thuần túy, bắt đầu bằng <p>.
"""

PROMPT_PART2 = """
Bạn là chuyên gia viết bài SEO. Viết PHẦN 2 (tiếp theo) của bài blog với tiêu đề: "{title}"

TỪ KHÓA SEO CHÍNH: "{keyword}"
CÔNG TY: THANG MÁY KENZO VIỆT NAM

CHỈ VIẾT PHẦN 2 (khoảng 800 TỪ), bao gồm:

1. <h2>Quy trình lắp đặt {keyword}</h2> (200 từ):
<p>Mô tả chi tiết các bước lắp đặt <strong>{keyword}</strong>:</p>
<ul>
<li>Bước 1: Khảo sát và tư vấn</li>
<li>Bước 2: Thiết kế và báo giá</li>
<li>Bước 3: Thi công lắp đặt</li>
<li>Bước 4: Nghiệm thu và bàn giao</li>
</ul>

2. <h2>Kinh nghiệm chọn {keyword} phù hợp</h2> (200 từ):
<p>Chia sẻ kinh nghiệm, tiêu chí lựa chọn <strong>{keyword}</strong> chất lượng. Các yếu tố cần xem xét như thương hiệu, bảo hành, dịch vụ hậu mãi.</p>

3. <h2>Câu hỏi thường gặp về {keyword}</h2> (200 từ):
<h3>Câu hỏi 1: Chi phí lắp đặt {keyword} là bao nhiêu?</h3>
<p>Trả lời chi tiết về chi phí...</p>
<h3>Câu hỏi 2: Thời gian lắp đặt {keyword} mất bao lâu?</h3>
<p>Trả lời chi tiết về thời gian...</p>
<h3>Câu hỏi 3: Bảo trì {keyword} như thế nào?</h3>
<p>Trả lời chi tiết về bảo trì...</p>

4. <h2>Kết luận</h2> (200 từ):
<p>Tóm tắt các điểm chính về <strong>{keyword}</strong>. Kêu gọi khách hàng liên hệ THANG MÁY KENZO VIỆT NAM để được tư vấn và báo giá tốt nhất.</p>

QUY TẮC:
- CHỈ DÙNG HTML (<h2>, <h3>, <p>, <ul>, <li>, <strong>)
- KHÔNG dùng Markdown (##, **)
- Từ khóa "{keyword}" phải in đậm: <strong>{keyword}</strong>
- Mỗi phần PHẢI có ít nhất 200 từ

Xuất ra HTML thuần túy, bắt đầu bằng <h2>.
"""

CONTACT_SECTION = """
<h2>Liên hệ THANG MÁY KENZO VIỆT NAM</h2>
<p>Nếu bạn cần tư vấn về <strong>{keyword}</strong>, hãy liên hệ ngay với chúng tôi:</p>
<p><strong>CÔNG TY TNHH THANG MÁY KENZO VIỆT NAM</strong></p>
<ul>
<li>Trụ sở: 07 Đường DD5, Phường Tân Hưng Thuận, Quận 12, TP.HCM</li>
<li>Xưởng: B15/6A Liên Ấp 1-2-3, H. Bình Chánh, TP.HCM</li>
<li>Chi nhánh Bình Dương: 113, NE3, Chánh Phú Hoà, Bến Cát - ĐT: 0932 619 668</li>
<li>Chi nhánh Quy Nhơn: Tổ 15, Khu 2, P. Nhơn Bình - ĐT: 0937 596 248</li>
<li>Email: thanhtienelevator@gmail.com</li>
<li>Website: <a href="https://suachuathangmay247.com">suachuathangmay247.com</a> | <a href="https://thangmaykenzo.com">thangmaykenzo.com</a></li>
</ul>
"""


def clean_gemini_content(content: str, log_func=None) -> str:
    if not content:
        return content
    
    original_length = len(content)
    
    first_heading_match = re.search(r'<h[12][^>]*>', content, re.IGNORECASE)
    if first_heading_match:
        content = content[first_heading_match.start():]
    
    last_link_pos = -1
    website_patterns = [
        r'thangmaykenzo\.com[^<]*</a>',
        r'suachuathangmay247\.com[^<]*</a>',
        r'thangmaykenzo\.com[^<]*</li>',
        r'suachuathangmay247\.com[^<]*</li>',
    ]
    
    for pattern in website_patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            if match.end() > last_link_pos:
                last_link_pos = match.end()
    
    if last_link_pos > 0:
        remaining = content[last_link_pos:]
        end_list_match = re.search(r'(</li>\s*)*</ul>', remaining, re.IGNORECASE)
        if end_list_match:
            cut_point = last_link_pos + end_list_match.end()
            content = content[:cut_point]
    
    outro_patterns = [
        r'<h[23][^>]*>\s*Next Steps[^<]*</h[23]>.*$',
        r'<p>\s*Would you like me to.*$',
        r'<p>\s*Do you want me to.*$',
        r'<p>\s*Let me know if you.*$',
        r'<p>\s*Shall I.*$',
        r'<strong>\s*Next Steps.*$',
        r'\(Lưu ý:.*?\)',
        r'\(Ghi chú:.*?\)',
        r'\(Chú ý:.*?\)',
        r'\(Tham khảo:.*?\)',
        r'\(Note:.*?\)',
        r'</ul>\s*\n*\s*\(.*?\)\s*$',
        r'</p>\s*\n*\s*\(.*?\)\s*$',
        r'<p>\s*\(.*?SEO.*?\)\s*</p>\s*$',
        r'<p>\s*\(.*?bài viết.*?\)\s*</p>\s*$',
        r'<p>\s*\(.*?từ khóa.*?\)\s*</p>\s*$',
        r'\(.*?1500.*?chữ.*?\)',
        r'\(.*?phân bố rải rác.*?\)',
        r'\s*\([^)]{50,}\)\s*$',
    ]
    
    for pattern in outro_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.DOTALL)
    
    lines = content.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            continue
        if stripped.startswith('(') and stripped.endswith(')'):
            continue
        meta_keywords = [
            'để bài viết đạt', 'SEO', 'từ khóa', 'tỷ lệ từ khóa',
            'mật độ từ khóa', 'phân bố rải rác', 'lịch sử loài',
            'có thể bổ sung thêm', 'để đảm bảo', 'sức mạnh SEO'
        ]
        is_meta = stripped.startswith('(') and any(kw.lower() in stripped.lower() for kw in meta_keywords)
        if is_meta:
            continue
        cleaned_lines.append(line)
    
    content = '\n'.join(cleaned_lines)
    content = re.sub(r'\s*<p>\s*</p>\s*', '', content)
    content = re.sub(r'\s+$', '', content)
    content = re.sub(r'\s*\([^)]*$', '', content)
    
    cleaned_length = len(content)
    if original_length != cleaned_length and log_func:
        removed = original_length - cleaned_length
        log_func(f"Cleaned content: {original_length} → {cleaned_length} chars (-{removed})", "info")
    
    return content
