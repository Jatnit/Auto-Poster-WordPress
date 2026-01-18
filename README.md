# 🚀 WordPress Auto Poster

> **Tự động đăng bài viết lên WordPress với Gemini AI**

Ứng dụng tự động hóa việc tạo nội dung bằng Gemini AI và đăng lên WordPress. Hỗ trợ lên lịch bài viết, SEO với Rank Math, chèn hình ảnh tự động, thêm tags, và giao diện web Matrix-style.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)
![Playwright](https://img.shields.io/badge/Playwright-1.40+-purple.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## 📋 Mục lục

- [Tính năng](#-tính-năng)
- [Yêu cầu hệ thống](#-yêu-cầu-hệ-thống)
- [Cài đặt](#-cài-đặt)
- [Sử dụng](#-sử-dụng)
- [Cấu hình](#-cấu-hình)
- [Cấu trúc Project](#-cấu-trúc-project)
- [Xử lý lỗi](#-xử-lý-lỗi)

---

## ✨ Tính năng

| Tính năng                 | Mô tả                                                |
| ------------------------- | ---------------------------------------------------- |
| 🌐 **Gemini Web Chat**    | Tạo nội dung tự động bằng Gemini (MIỄN PHÍ)          |
| 📝 **Auto Post**          | Tự động đăng bài lên WordPress (Classic Editor)      |
| 📅 **Scheduling**         | Lên lịch đăng bài theo ngày (tùy chỉnh số bài/ngày)  |
| 🏷️ **SEO Ready**          | Tích hợp Rank Math SEO keywords                      |
| 🏷️ **Auto Tags**          | Tự động thêm tags cho mỗi bài viết                   |
| 🖼️ **Auto Images**        | Tự động chèn 3 hình ảnh vào nội dung (H2 #1, #3, #5) |
| 🎨 **Matrix UI**          | Giao diện web Matrix Hacker style                    |
| 📊 **Real-time Progress** | Theo dõi tiến trình trực tiếp                        |
| ⏸️ **Pause/Resume**       | Tạm dừng và tiếp tục bất cứ lúc nào                  |
| 💾 **Site Presets**       | Lưu cấu hình nhiều website WordPress                 |

---

## 💻 Yêu cầu hệ thống

- **Python**: 3.9 trở lên (khuyến nghị 3.10+)
- **Browser**: Chromium hoặc Brave Browser
- **WordPress**: Classic Editor plugin (không phải Gutenberg)
- **Rank Math**: Plugin SEO (tùy chọn, để set focus keyword)

---

## 📦 Cài đặt

### 1. Clone repository

```bash
git clone https://github.com/Jatnit/Auto-Poster-WordPress.git
cd Auto-Poster-WordPress
```

### 2. Tạo Virtual Environment

```bash
python3 -m venv .venv
```

### 3. Kích hoạt Virtual Environment

```bash
# macOS/Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 4. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 5. Cài đặt Playwright browsers

```bash
playwright install chromium
```

### 6. (Tùy chọn) Cài đặt Brave Browser

Nếu muốn sử dụng Brave Browser để tránh lỗi đăng nhập Google:

- Tải tại: https://brave.com/download/

---

## 🌐 Sử dụng

### ▶️ Khởi động Web Server

```bash
# Kích hoạt virtual environment (nếu chưa)
source .venv/bin/activate  # macOS/Linux
# hoặc
.venv\Scripts\activate  # Windows

# Chạy ứng dụng
python app.py
```

Mở trình duyệt và truy cập: **http://localhost:5000**

### 📝 Quy trình sử dụng

1. **Cấu hình WordPress**
   - Nhập WordPress Username, Password
   - Nhập WordPress Login URL (`https://your-site.com/wp-login.php`)
   - Nhập WordPress Admin URL (`https://your-site.com/wp-admin`)
   - Lưu cấu hình

2. **Thêm Topics** (2 chế độ)

   **Chế độ 1: Nhiều tiêu đề + 1 từ khóa + 1 tags (chung)**
   - Nhập từ khóa SEO chung
   - Nhập tags (phân cách bằng dấu phẩy)
   - Nhập nhiều tiêu đề (mỗi dòng 1 tiêu đề)
   - Click "Thêm tất cả tiêu đề"

   **Chế độ 2: Mỗi tiêu đề + từ khóa + tags riêng**
   - Nhập tiêu đề, từ khóa, tags cho từng bài
   - Click nút "+"

3. **Bắt đầu**
   - Click "▶ Bắt đầu"
   - Browser sẽ mở ra
   - **Đăng nhập Google** khi được yêu cầu (có 10 phút timeout)
   - Ứng dụng sẽ tự động:
     - Tạo nội dung với Gemini
     - Đăng nhập WordPress
     - Tạo bài viết với tiêu đề, nội dung
     - Chèn 3 hình ảnh vào content
     - Set Rank Math keyword
     - Thêm tags
     - Chọn category
     - Xuất bản hoặc lên lịch

### ⏸️ Tạm dừng / Dừng

- **Tạm dừng**: Click "⏸ Tạm dừng" để pause, click lại để tiếp tục
- **Dừng**: Click "⏹ Dừng" để dừng hoàn toàn

### ⏹️ Tắt Web Server

```bash
Ctrl + C
```

---

## ⚙️ Cấu hình

### Thông tin cần thiết

| Trường              | Mô tả                             | Ví dụ                           |
| ------------------- | --------------------------------- | ------------------------------- |
| WordPress Username  | Tài khoản admin WordPress         | `admin`                         |
| WordPress Password  | Mật khẩu WordPress                | `your-password`                 |
| WordPress Login URL | URL trang đăng nhập               | `https://site.com/wp-login.php` |
| WordPress Admin URL | URL trang quản trị                | `https://site.com/wp-admin`     |
| Số bài/ngày         | Số bài đăng mỗi ngày              | `2`                             |
| Delay giữa các bài  | Thời gian chờ giữa các bài (giây) | `65`                            |
| Headless Mode       | Ẩn/hiện browser khi chạy          | `off`                           |

### Prompt Template

Tùy chỉnh prompt template trong phần cấu hình. Sử dụng:

- `{title}` - Tiêu đề bài viết
- `{keyword}` - Từ khóa SEO

**Ví dụ:**

```
Viết bài blog chuẩn SEO với tiêu đề "{title}".
Từ khóa SEO "{keyword}". Từ khóa in đậm.
Bài viết trên 1500 từ, có các tiêu đề H2/H3.
Mật độ từ khóa không vượt quá 3%.
```

### Lưu cấu hình nhiều website

- Click "💾 Lưu" sau khi điền thông tin
- Chọn từ dropdown để load cấu hình đã lưu
- Mỗi website một preset riêng

---

## 📁 Cấu trúc Project

```
Auto-Poster-WordPress/
├── .venv/                    # Virtual environment
├── ai_providers/             # AI provider modules
│   ├── __init__.py
│   ├── ollama.py            # Ollama integration
│   └── gemini_api.py        # Gemini API integration
├── wordpress/                # WordPress automation modules
│   ├── __init__.py
│   ├── auth.py              # Login handling
│   ├── editor.py            # Title, content, SEO
│   ├── media.py             # Image handling
│   └── publish.py           # Publish/schedule
├── templates/
│   └── index.html           # Web interface (Matrix theme)
├── app.py                   # Flask web server + main automation
├── config.py                # Configuration & state management
├── prompts.py               # Prompt templates
├── requirements.txt         # Python dependencies
└── README.md                # Documentation
```

---

## 📊 Workflow

```
1. Khởi động app
   └── python app.py

2. Mở browser → http://localhost:5000

3. Cấu hình
   ├── WordPress credentials
   ├── Prompt template (tùy chọn)
   └── Thêm topics + keywords + tags

4. Click "Bắt đầu"

5. Browser mở
   └── Đăng nhập Google (nếu cần)

6. Tự động
   ├── Gemini tạo content (1500+ từ)
   ├── Đăng nhập WordPress
   ├── Tạo bài viết mới
   ├── Thêm tiêu đề, nội dung
   ├── Set Rank Math keyword
   ├── Chèn 3 hình ảnh vào content (sau H2 #1, #3, #5)
   ├── Thêm tags
   ├── Chọn category
   └── Xuất bản/Lên lịch

7. Hoàn thành!
```

---

## 🚨 Xử lý lỗi

### Lỗi: "Could not find Gemini input area"

**Nguyên nhân:** Chưa đăng nhập Google hoặc giao diện Gemini đã thay đổi

**Giải pháp:**

- Đảm bảo đã đăng nhập Google thành công trong browser
- Kiểm tra browser có hiển thị trang Gemini Chat không
- Thử refresh lại trang

### Lỗi: "Login failed: Still on login page"

**Kiểm tra:**

- URL login đúng chưa (`/wp-login.php`)
- Username/password đúng chưa
- Website có bật 2FA không (cần tắt)
- Có plugin security nào block không

### Lỗi: Chỉ chèn được 1 hình thay vì 3

**Nguyên nhân:** DOM elements bị stale sau khi insert

**Giải pháp:** Đã được fix trong version mới. Cập nhật code:

```bash
git pull origin main
```

### Lỗi: Port 5000 đang được sử dụng

**Giải pháp:**

```bash
# macOS/Linux - Tìm và kill process
lsof -i :5000
kill -9 <PID>

# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

### Lỗi: "command not found: python"

**Giải pháp:** Sử dụng `python3` thay vì `python`:

```bash
python3 app.py
```

---

## 🔧 Các lệnh thường dùng

| Lệnh                              | Mô tả                        |
| --------------------------------- | ---------------------------- |
| `source .venv/bin/activate`       | Kích hoạt venv (macOS/Linux) |
| `.venv\Scripts\activate`          | Kích hoạt venv (Windows)     |
| `deactivate`                      | Thoát virtual environment    |
| `python app.py`                   | Chạy web server              |
| `Ctrl + C`                        | Dừng web server              |
| `pip install -r requirements.txt` | Cài đặt dependencies         |
| `pip freeze > requirements.txt`   | Xuất dependencies            |

---

## 🛠️ Phát triển

### Thêm AI Provider mới

1. Tạo file trong `ai_providers/`
2. Implement function `generate_content_<provider>(title, keyword)`
3. Import và expose trong `ai_providers/__init__.py`
4. Thêm vào `generate_content()` trong `app.py`

### Thêm WordPress function mới

1. Tạo hoặc edit file trong `wordpress/`
2. Implement function với parameters `(page, config, log_func)`
3. Import trong `app.py` hoặc gọi trực tiếp

---

## 📞 Hỗ trợ

Nếu gặp vấn đề:

1. Kiểm tra logs trong giao diện web
2. Xem terminal output để debug
3. Đảm bảo đã kích hoạt virtual environment
4. Tạo issue trên GitHub với thông tin chi tiết

---

## 📄 License

MIT License - Sử dụng tự do cho mục đích cá nhân và thương mại.

---

## 🙏 Credits

- [Playwright](https://playwright.dev/) - Browser automation
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Google Gemini](https://gemini.google.com/) - AI content generation
