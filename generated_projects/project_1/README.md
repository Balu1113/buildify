# TODO App - Production-Ready End-to-End Application

A professional, full-stack task management application designed with a focus on security, scalability, and user experience. This application provides a complete end-to-end solution for managing personal tasks with robust authentication and advanced data management capabilities.

## 🚀 Features

### Authentication & Security
- **JWT Authentication:** Secure login and registration using JSON Web Tokens (Access and Refresh tokens).
- **User Isolation:** Strict server-side logic ensuring users can only access, update, or delete their own TODO items.
- **Protected Routes:** Frontend routes are secured to prevent unauthorized access to the dashboard.
- **Session Management:** Automatic handling of expired tokens via refresh token rotation.

### TODO Management
- **Full CRUD Operations:** Create, Read, Update, and Delete tasks seamlessly.
- **Advanced Data Handling:**
  - **Search:** Real-time searching by title and description.
  - **Filtering:** Filter tasks by status, priority, and due date.
  - **Sorting:** Sort tasks by creation date, due date, priority level, or status.
  - **Pagination:** Efficient server-side pagination for large datasets.
- **Task Metadata:** Track titles, descriptions, status (pending/completed), priority (low/medium/high), and due dates.

### Dashboard & UX
- **Metrics Dashboard:** Instant overview of total, pending, completed, and high-priority tasks.
- **Responsive Design:** Fully optimized interface for desktop, tablet, and mobile devices.
- **Robust UX:** Integrated loading states, empty states, form validation, and comprehensive error handling for API failures.

## 🛠 Tech Stack

**Frontend**
- **Framework:** React.js (via Vite)
- **Styling:** Tailwind CSS
- **API Client:** Axios (with interceptors for JWT)
- **State Management:** React Context API

**Backend**
- **Framework:** Django & Django REST Framework (DRF)
- **Authentication:** SimpleJWT
- **Database:** PostgreSQL
- **Filtering/Search:** django-filter

**DevOps & Tools**
- **Containerization:** Docker & Docker Compose
- **Environment Management:** Dotenv
- **Testing:** Pytest

## 📂 Project Structure

```text
todo-app/
├── backend/                # Django REST Framework application
│   ├── apps/               # Modular apps (accounts, todos)
│   ├── config/             # Project settings and core URLs
│   ├── manage.py           # Django CLI
│   └── requirements.txt    # Python dependencies
├── frontend/               # React.js application
│   ├── src/
│   │   ├── api/            # Axios services & interceptors
│   │   ├── components/     # Reusable UI & feature components
│   │   ├── context/        # Authentication state
│   │   ├── pages/          # Route-level components
│   │   └── routes/         # Protected route logic
│   ├── vite.config.js      # Vite configuration
│   └── package.json        # Node dependencies
├── .env.example            # Template for environment variables
├── docker-compose.yml      # Orchestration for Backend, Frontend, and DB
└── README.md
```

## ⚙️ Installation & Setup

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### Running with Docker (Recommended)

The quickest way to get the entire stack up and running is using Docker Compose.

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd todo-app
   ```

2. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   ```
   *Note: Edit `.env` to customize your `SECRET_KEY`, `DATABASE_URL`, and `CORS_ALLOWED_ORIGINS`.*

3. **Build and Start Containers:**
   ```bash
   docker-compose up --build
   ```

4. **Access the Application:**
   - **Frontend:** [http://localhost:5173](http://localhost:5173)
   - **Backend API:** [http://localhost:8000](http://localhost:8000)

---

### Local Development (Manual Setup)

#### Backend Setup
1. Navigate to `backend/`:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```
2. Configure your local PostgreSQL instance and update `.env`.
3. Run migrations and start the server:
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

#### Frontend Setup
1. Navigate to `frontend/`:
   ```bash
   cd frontend
   npm ci
   ```
2. Start the development server:
   ```bash
   npm run dev
   ```

## 🔌 API Endpoints

### Authentication
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/accounts/register/` | `POST` | Register a new user |
| `/api/accounts/login/` | `POST` | Obtain Access & Refresh tokens |
| `/api/accounts/token/refresh/` | `POST` | Obtain new Access token |
| `/api/accounts/logout/` | `POST` | Invalidate session |

### TODOs (Authenticated)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/todos/` | `GET` | List TODOs (supports search, filter, sort, pagination) |
| `/api/todos/` | `POST` | Create a new TODO |
| `/api/todos/<id>/` | `GET` | Retrieve a specific TODO |
| `/api/todos/<id>/` | `PUT/PATCH` | Update a TODO |
| `/api/todos/<id>/` | `DELETE` | Delete a TODO |
| `/api/todos/dashboard/` | `GET` | Get summary metrics |

### Health Check
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/health/` | `GET` | Check backend service status |