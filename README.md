# 🚀 WordPress Auto Poster

> **Tự động đăng bài viết lên WordPress với Gemini Web Chat**

Ứng dụng tự động hóa việc tạo nội dung bằng Gemini AI và đăng lên WordPress. Hỗ trợ lên lịch bài viết, SEO với Rank Math, chèn hình ảnh tự động, và giao diện web dễ sử dụng.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)
![Playwright](https://img.shields.io/badge/Playwright-1.40+-purple.svg)

---

## 📋 Mục lục

- [Tính năng](#-tính-năng)
- [Cài đặt](#-cài-đặt)
- [Sử dụng](#-sử-dụng)
- [Cấu hình](#-cấu-hình)
- [Xử lý lỗi](#-xử-lý-lỗi)

---

## ✨ Tính năng

| Tính năng                 | Mô tả                                               |
| ------------------------- | --------------------------------------------------- |
| 🌐 **Gemini Web Chat**    | Tạo nội dung tự động bằng Gemini (MIỄN PHÍ)         |
| 📝 **Auto Post**          | Tự động đăng bài lên WordPress (Classic Editor)     |
| 📅 **Scheduling**         | Lên lịch 2 bài/ngày (9h sáng & 3h chiều)            |
| 🏷️ **SEO Ready**          | Tích hợp Rank Math SEO keywords                     |
| 🖼️ **Auto Images**        | Tự động chèn hình ảnh vào nội dung + Featured Image |
| 🎨 **Web Interface**      | Giao diện web hiện đại, dark mode                   |
| 📊 **Real-time Progress** | Theo dõi tiến trình trực tiếp                       |
| 📝 **Custom Prompt**      | Tùy chỉnh prompt template cho Gemini                |

---

## 📦 Cài đặt

### 1. Clone hoặc tải project

```bash
cd /Users/jatnit/Documents/Workflow
```

### 2. Tạo Virtual Environment (nếu chưa có)

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

### 5. Cài đặt Brave Browser

Ứng dụng sử dụng Brave Browser để tránh lỗi đăng nhập Google. Tải tại: https://brave.com/download/

---

## 🌐 Sử dụng

### ▶️ Khởi động Web Server

```bash
cd /Users/jatnit/Documents/Workflow
source .venv/bin/activate
python app.py
```

Sau khi chạy, mở trình duyệt và truy cập:

👉 **http://localhost:5000**

### 📝 Quy trình sử dụng

1. **Cấu hình WordPress**

   - Nhập WordPress Username, Password
   - Nhập WordPress Login URL (`https://your-site.com/wp-login.php`)
   - Nhập WordPress Admin URL (`https://your-site.com/wp-admin`)

2. **Cấu hình Prompt**

   - Tùy chỉnh prompt template trong ô "Prompt Template"
   - Sử dụng `{title}` và `{keyword}` để chèn tiêu đề và từ khóa

3. **Thêm Topics**

   - Nhập tiêu đề bài viết
   - Nhập từ khóa SEO
   - Click "Thêm"

4. **Bắt đầu**
   - Click "Bắt đầu"
   - Brave Browser sẽ mở ra
   - **Đăng nhập Google** khi được yêu cầu (có 10 phút)
   - Ứng dụng sẽ tự động tạo nội dung và đăng bài

### ⏹️ Dừng Web Server

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
| Prompt Template     | Mẫu prompt cho Gemini             | Xem bên dưới                    |
| Số bài/ngày         | Số bài đăng mỗi ngày              | `2`                             |
| Delay giữa các bài  | Thời gian chờ giữa các bài (giây) | `30`                            |

### Prompt Template mẫu

```
Viết bài blog chuẩn SEO google với tiêu đề "{title}".
THANG MÁY KENZO VIỆT NAM chuyên lắp đặt, sửa chữa, bảo trì thang máy.
Từ khóa SEO "{keyword}". Từ khóa in đậm, bài viết trên 1500 từ.
Từ khóa SEO lặp lại không vượt quá 3%.
```

---

## 📁 Cấu trúc Project

```
Workflow/
├── .venv/                    # Virtual environment
├── templates/
│   └── index.html           # Giao diện web
├── app.py                   # Flask web server + automation
├── requirements.txt         # Dependencies
└── README.md               # File này
```

---

## 🚨 Xử lý lỗi

### Lỗi: "Could not find Gemini input area"

**Nguyên nhân:** Giao diện Gemini đã thay đổi

**Giải pháp:**

- Đảm bảo đã đăng nhập Google thành công
- Kiểm tra browser có hiển thị trang Gemini Chat không
- Thử refresh lại trang

### Lỗi: "Login failed: Still on login page"

**Kiểm tra:**

- URL login đúng chưa (`/wp-login.php`)
- Username/password đúng chưa
- Website có bật 2FA không (cần tắt)
- Có plugin security nào block không

### Lỗi: Modal chọn hình bị treo

**Nguyên nhân:** Media modal không đóng đúng cách

**Giải pháp:** Đã được sửa tự động, nếu vẫn xảy ra:

- Đóng modal thủ công và tiếp tục
- Hoặc dừng và chạy lại

### Lỗi: Port 5000 đang được sử dụng

**Giải pháp:**

```bash
# Tìm và kill process
lsof -i :5000
kill -9 <PID>
```

### Lỗi: "command not found: python"

**Giải pháp:** Sử dụng đường dẫn đầy đủ:

```bash
/Users/jatnit/Documents/Workflow/.venv/bin/python app.py
```

---

## 📊 Workflow

```
1. Khởi động app
   └── python app.py

2. Mở browser → http://localhost:5000

3. Cấu hình
   ├── WordPress credentials
   ├── Prompt template
   └── Thêm topics

4. Click "Bắt đầu"

5. Brave Browser mở
   └── Đăng nhập Google (nếu cần)

6. Tự động
   ├── Gemini tạo content (1500+ từ)
   ├── Đăng nhập WordPress
   ├── Tạo bài viết mới
   ├── Thêm tiêu đề, nội dung
   ├── Chèn 3 hình ảnh vào content
   ├── Đặt featured image
   ├── Set Rank Math keyword
   ├── Chọn category
   └── Xuất bản/Lên lịch

7. Hoàn thành!
```

---

## 🔧 Các lệnh thường dùng

| Lệnh                              | Mô tả                         |
| --------------------------------- | ----------------------------- |
| `source .venv/bin/activate`       | Kích hoạt virtual environment |
| `deactivate`                      | Thoát virtual environment     |
| `python app.py`                   | Chạy web server               |
| `Ctrl + C`                        | Dừng web server               |
| `pip install -r requirements.txt` | Cài đặt dependencies          |

---

## 📞 Hỗ trợ

Nếu gặp vấn đề:

1. Kiểm tra logs trong giao diện web
2. Xem terminal output để debug
3. Đảm bảo đã kích hoạt virtual environment
4. Đảm bảo Brave Browser đã được cài đặt

---

## 📄 License

MIT License - Sử dụng tự do cho mục đích cá nhân và thương mại.
