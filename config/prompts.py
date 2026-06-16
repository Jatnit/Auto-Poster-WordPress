import os
import sys

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from wp_auto_poster.content.cleanup import clean_generated_content

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
    """Backward-compatible wrapper around the extracted content cleanup helper."""
    return clean_generated_content(content, log_func=log_func)
