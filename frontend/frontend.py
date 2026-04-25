import streamlit as st
import requests
import base64
import urllib.parse
from streamlit_cookies_manager import EncryptedCookieManager

st.set_page_config(page_title="Simple Social", layout="wide")

BASE_URL = "http://localhost:8000"

# -----------------------
# 🍪 Cookie Manager
# -----------------------
cookies = EncryptedCookieManager(
    prefix="myapp/",
    password="SUPER_SECRET_KEY"
)

if not cookies.ready():
    st.stop()

# -----------------------
# Session state
# -----------------------
if "access_token" not in st.session_state:
    st.session_state.access_token = cookies.get("access_token")

if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = cookies.get("refresh_token")

if "user" not in st.session_state:
    st.session_state.user = None


# -----------------------
# Helpers
# -----------------------
def get_headers():
    if st.session_state.access_token:
        return {"Authorization": f"Bearer {st.session_state.access_token}"}
    return {}


def save_tokens(access, refresh):
    st.session_state.access_token = access
    st.session_state.refresh_token = refresh

    cookies["access_token"] = access
    cookies["refresh_token"] = refresh
    cookies.save()


def clear_tokens():
    st.session_state.access_token = None
    st.session_state.refresh_token = None
    st.session_state.user = None

    cookies["access_token"] = ""
    cookies["refresh_token"] = ""
    cookies.save()


def refresh_access_token():
    if not st.session_state.refresh_token:
        return False

    response = requests.post(
        f"{BASE_URL}/auth/refresh",
        json={"refresh_token": st.session_state.refresh_token}
    )

    if response.status_code == 200:
        new_token = response.json()["access_token"]
        st.session_state.access_token = new_token
        cookies["access_token"] = new_token
        cookies.save()
        return True

    return False


def authorized_request(method, url, **kwargs):
    headers = get_headers()
    response = requests.request(method, url, headers=headers, **kwargs)

    if response.status_code == 401:
        success = refresh_access_token()

        if success:
            headers = get_headers()
            return requests.request(method, url, headers=headers, **kwargs)

        clear_tokens()
        st.warning("Session expired. Please login again.")
        st.rerun()

    return response


# -----------------------
# Restore session after refresh
# -----------------------
if st.session_state.access_token and st.session_state.user is None:
    user_response = authorized_request("GET", f"{BASE_URL}/users/me")

    if user_response.status_code == 200:
        st.session_state.user = user_response.json()


# -----------------------
# Auth Page
# -----------------------
def login_page():
    st.title("🚀 Welcome to Simple Social")

    email = st.text_input("Email:")
    password = st.text_input("Password:", type="password")

    if email and password:
        col1, col2 = st.columns(2)

        # LOGIN
        with col1:
            if st.button("Login", use_container_width=True):
                response = requests.post(
                    f"{BASE_URL}/auth/login",
                    data={"username": email, "password": password}
                )

                if response.status_code == 200:
                    data = response.json()

                    save_tokens(
                        data["access_token"],
                        data["refresh_token"]
                    )

                    user_response = authorized_request(
                        "GET",
                        f"{BASE_URL}/users/me"
                    )

                    if user_response.status_code == 200:
                        st.session_state.user = user_response.json()
                        st.rerun()
                    else:
                        st.error("Failed to get user info")

                else:
                    st.error("Invalid email or password!")

        # SIGNUP
        with col2:
            if st.button("Sign Up", use_container_width=True):
                response = requests.post(
                    f"{BASE_URL}/auth/register",
                    json={"email": email, "password": password}
                )

                if response.status_code == 201:
                    st.success("Account created! Login now.")
                else:
                    st.error("Registration failed")


# -----------------------
# Upload
# -----------------------
def upload_page():
    st.title("📸 Share Something")

    uploaded_file = st.file_uploader(
        "Choose media",
        type=['png', 'jpg', 'jpeg', 'mp4']
    )

    caption = st.text_area("Caption")

    if uploaded_file and st.button("Share"):
        files = {
            "file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)
        }

        response = authorized_request(
            "POST",
            f"{BASE_URL}/upload",
            files=files,
            data={"caption": caption}
        )

        if response.status_code == 200:
            st.success("Posted!")
            st.rerun()
        else:
            st.error("Upload failed")


def encode_text_for_overlay(text):
    if not text:
        return ""
    base64_text = base64.b64encode(text.encode('utf-8')).decode('utf-8')
    return urllib.parse.quote(base64_text)


def create_transformed_url(original_url, transformation_params, caption=None):
    if caption:
        encoded_caption = encode_text_for_overlay(caption)
        transformation_params = f"l-text,ie-{encoded_caption},ly-N20,lx-20,fs-100,co-white,bg-000000A0,l-end"

    if not transformation_params:
        return original_url

    parts = original_url.split("/")
    base_url = "/".join(parts[:4])
    file_path = "/".join(parts[4:])

    return f"{base_url}/tr:{transformation_params}/{file_path}"

# -----------------------
# Feed
# -----------------------
def feed_page():
    st.title("🏠 Feed")

    user = st.session_state.user
    current_user_id = user["id"]
    current_user_role = user.get("role", "user")

    response = authorized_request("GET", f"{BASE_URL}/feed")

    if response.status_code == 200:
        posts = response.json()["posts"]

        for post in posts:
            st.markdown("---")

            col1, col2 = st.columns([4, 1])

            with col1:
                st.markdown(f"**{post['email']}** • {post['created_at'][:10]}")

            with col2:
                is_owner = post["user_id"] == current_user_id
                is_admin = current_user_role.lower() == "admin"

                if is_owner or is_admin:
                    if st.button("🗑️", key=f"del_{post['id']}"):
                        res = authorized_request(
                            "DELETE",
                            f"{BASE_URL}/posts/{post['id']}"
                        )

                        if res.status_code == 200:
                            st.success("Deleted")
                            st.rerun()

            caption = post.get("caption", "")

            if post["file_type"] == "image":
                st.image(create_transformed_url(post["url"], "", caption), width=300)
            else:
                st.video(post["url"], width=300)
                st.caption(caption)


# -----------------------
# Admin Dashboard
# -----------------------
def admin_dashboard_page():
    st.title("📊 Admin Dashboard")

    response = authorized_request(
        "GET",
        f"{BASE_URL}/admin/dashboard"
    )

    if response.status_code == 200:
        data = response.json()
        st.metric("👥 Total Users", data["total_users"])
    else:
        st.error("Access denied")


# -----------------------
# Main
# -----------------------
if st.session_state.user is None:
    login_page()
else:
    st.sidebar.title(f"👋 {st.session_state.user['email']}")

    if st.sidebar.button("Logout"):
        clear_tokens()
        st.rerun()

    pages = ["🏠 Feed", "📸 Upload"]

    if st.session_state.user.get("role") == "admin":
        pages.append("📊 Dashboard")

    page = st.sidebar.radio("Navigate", pages)

    if page == "🏠 Feed":
        feed_page()
    elif page == "📸 Upload":
        upload_page()
    else:
        admin_dashboard_page()