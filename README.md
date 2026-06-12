# Virtual Stylist 👔👗

An AI-powered virtual try-on application that lets users visualize how clothes will look on them before buying. Built with Next.js, FastAPI, and Kling AI.

![Virtual Stylist Preview](https://via.placeholder.com/800x400?text=Virtual+Stylist+Preview)

## ✨ Features

- **AI Virtual Try-On**: Upload your photo and see how different outfits look on you using Kling AI
- **Wardrobe Management**: Organize clothes by category (tops, bottoms, dresses, shoes, accessories)
- **Multi-Garment Support**: Try on complete outfits (top + bottom combinations) with sequential processing
- **Avatar System**: Create and manage multiple avatars for different looks
- **Outfit Saving**: Save and organize your favorite outfit combinations
- **Real-Time Processing**: Fast AI-powered garment transfer using Kling AI Kolors v1.5
- **JWT Authentication**: Secure user authentication with session management

## 🏗️ Tech Stack

**Frontend:**
- Next.js 16 + React 19
- TypeScript
- Tailwind CSS v4

**Backend:**
- FastAPI (Python)
- Kling AI API for virtual try-on
- JWT authentication
- HTTPX for async HTTP requests

**AI/ML:**
- Kling AI Virtual Try-On (Kolors v1.5)
- Supports single and multi-garment processing
- Sequential garment application for realistic layering

**Deployment:**
- Vercel (Frontend + Serverless Backend)
- Environment-based configuration

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- Node.js 18+
- Kling AI API credentials ([Sign up here](https://www.klingai.com/))

### 1. Clone the Repository

```bash
git clone https://github.com/urdip/virtual-stylist.git
cd virtual-stylist
```

### 2. Setup Backend

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file in the root directory:

```env
KLINGAI_ACCESS_KEY=your_klingai_access_key
KLINGAI_SECRET_KEY=your_klingai_secret_key
BACKEND_PUBLIC_BASE=http://localhost:8000
CORS_ORIGINS=http://localhost:3000
```

Start the backend server:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 3. Setup Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the App

Navigate to http://localhost:3000 in your browser.

## 📸 Screenshots

| Wardrobe Selection | Try-On Result |
|-------------------|---------------|
| ![Wardrobe](https://via.placeholder.com/400x300?text=Wardrobe+Selection) | ![Result](https://via.placeholder.com/400x300?text=Try-On+Result) |

## 🔑 Environment Variables

### Backend

| Variable | Description | Required |
|----------|-------------|----------|
| `KLINGAI_ACCESS_KEY` | Kling AI API access key | Yes |
| `KLINGAI_SECRET_KEY` | Kling AI API secret key | Yes |
| `BACKEND_PUBLIC_BASE` | Backend URL (default: http://localhost:8000) | No |
| `CORS_ORIGINS` | Allowed frontend origins, comma-separated (default: http://localhost:3000) | No |
| `UPLOADS_DIR` | Uploads directory path (default: uploads or /tmp/uploads on Vercel) | No |
| `VERCEL` | Set to '1' when running on Vercel | No |

### Frontend

| Variable | Description | Required |
|----------|-------------|----------|
| `NEXT_PUBLIC_BACKEND_BASE` | Backend API base URL | No (defaults to http://localhost:8000) |

## 📁 Project Structure

```
virtual-stylist/
├── api/
│   └── app.py                 # Vercel serverless entry point
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI application & routes
│   │   ├── klingai_client.py  # Kling AI integration
│   │   ├── auth.py            # User authentication logic
│   │   ├── avatars.py         # Avatar management
│   │   ├── outfits.py         # Saved outfits management
│   │   └── __init__.py
│   └── uploads/               # User uploads storage (local dev)
├── frontend/
│   ├── app/                   # Next.js App Router pages
│   │   ├── builder/           # Main try-on interface
│   │   ├── avatar/            # Avatar management page
│   │   ├── login/             # Login page
│   │   ├── register/          # Registration page
│   │   ├── page.tsx           # Landing page
│   │   ├── layout.tsx         # Root layout
│   │   └── globals.css        # Global styles
│   ├── src/
│   │   └── lib/
│   │       └── api.ts         # API client & types
│   ├── package.json
│   └── next.config.ts
├── requirements.txt           # Python dependencies
├── vercel.json               # Vercel deployment config
└── README.md
```

## 🎯 How It Works

### Try-On Flow

1. **Upload Profile Photo**: User uploads their photo or creates an avatar
2. **Build Wardrobe**: Upload clothing items categorized by type (tops, bottoms, etc.)
3. **Select Outfit**: Choose garments to try on (single or multiple items)
4. **AI Processing**: Kling AI processes the images using sequential garment application
5. **View Result**: See a realistic visualization of yourself wearing the outfit
6. **Save Outfit**: Optionally save the outfit for later reference

### Multi-Garment Processing

When selecting both a top and bottom:
- Bottom garment (pants) is applied first
- Top garment (shirt) is applied over the result
- This ensures proper layering and realistic appearance

The system uses Kling AI's Kolors v1.5 model for high-quality virtual try-on results.

## 🛠️ Development

### Backend API Endpoints

#### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Register new user |
| `/auth/login` | POST | User login |
| `/auth/logout` | POST | User logout |
| `/auth/me` | GET | Get current user |
| `/auth/photo` | POST | Upload profile photo |
| `/auth/photo` | DELETE | Delete profile photo |
| `/auth/profile` | PUT | Update user profile (name/photo) |
| `/auth/change-password` | POST | Change password |

#### Wardrobe
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/wardrobe/upload` | POST | Upload clothing item |
| `/wardrobe/list` | GET | List wardrobe items (optionally filter by category) |
| `/wardrobe/{category}/{file_id}` | DELETE | Delete wardrobe item |

#### Avatars
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/avatars` | GET | List all avatars |
| `/avatars` | POST | Create new avatar |
| `/avatars/active` | GET | Get active avatar |
| `/avatars/{id}` | PUT | Update avatar |
| `/avatars/{id}` | DELETE | Delete avatar |
| `/avatars/{id}/activate` | POST | Set avatar as active |

#### Try-On
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tryon` | POST | Generate try-on with single garment (backward compatible) |
| `/tryon/outfit` | POST | Generate try-on with multiple garments |

#### Outfits
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/outfits` | GET | List saved outfits |
| `/outfits` | POST | Save a new outfit |
| `/outfits/{id}` | PUT | Rename outfit |
| `/outfits/{id}` | DELETE | Delete outfit |

#### Files
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/uploads/{path}` | GET | Serve uploaded files |

### Running Tests

```bash
# Backend tests (if available)
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## 🚀 Deployment

### Vercel Deployment

This project is configured for Vercel deployment with both frontend and backend:

1. Connect your GitHub repository to Vercel
2. Set environment variables in Vercel dashboard:
   - `KLINGAI_ACCESS_KEY`
   - `KLINGAI_SECRET_KEY`
   - `BACKEND_PUBLIC_BASE` (your Vercel deployment URL)
3. Deploy!

The `vercel.json` configuration handles routing between the static frontend and serverless backend functions.

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 🙏 Acknowledgments

- [Kling AI](https://www.klingai.com/) for providing the virtual try-on API
- [Next.js](https://nextjs.org/) for the frontend framework
- [FastAPI](https://fastapi.tiangolo.com/) for the backend framework
- [Tailwind CSS](https://tailwindcss.com/) for styling

## 📧 Contact

**Urdip Jadeja** - [@UrdipJadeja](https://github.com/urdip) - Jadejaurdip@gmail.com

Project Link: [https://github.com/urdip/virtual-stylist](https://github.com/urdip/virtual-stylist)

---

**Note**: This project requires Kling AI API credentials. Virtual Try-On credits need to be purchased separately from Kling AI platform.
