import streamlit as st
import requests
import base64
import urllib.parse

st.set_page_config(page_title="Simple Social", layout="wide")

# -----------------------
# Session state
# -----------------------
if 'token' not in st.session_state:
    st.session_state.token = None
if 'user' not in st.session_state:
    st.session_state.user = None
if 'password' not in st.session_state:
    st.session_state.password = None


# -----------------------
# Helpers
# -----------------------
def get_headers():
    if st.session_state.token:
        return {"Authorization": f"Bearer {st.session_state.token}"}
    return {}


def re_login():
    """
    OPTION A: re-authenticate using email + password
    """
    if not st.session_state.user or not st.session_state.password:
        return False

    response = requests.post(
        "http://localhost:8000/auth/login",
        data={
            "username": st.session_state.user["email"],
            "password": st.session_state.password
        }
    )

    if response.status_code == 200:
        token_data = response.json()
        st.session_state.token = token_data["access_token"]
        return True

    return False


def authorized_request(method, url, **kwargs):
    headers = get_headers()
    response = requests.request(method, url, headers=headers, **kwargs)

    if response.status_code == 401:
        # 🔁 OPTION A: re-login
        success = re_login()

        if success:
            headers = get_headers()
            return requests.request(method, url, headers=headers, **kwargs)

        else:
            st.session_state.user = None
            st.session_state.token = None
            st.session_state.password = None
            st.warning("Session expired. Please login again.")
            st.rerun()

    return response


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
            if st.button("Login", type="primary", use_container_width=True):
                response = requests.post(
                    "http://localhost:8000/auth/login",
                    data={
                        "username": email,
                        "password": password
                    }
                )

                if response.status_code == 200:
                    token_data = response.json()

                    st.session_state.token = token_data["access_token"]
                    st.session_state.password = password  # 🔥 REQUIRED FOR OPTION A

                    # get user
                    user_response = authorized_request(
                        "GET",
                        "http://localhost:8000/users/me"
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
            if st.button("Sign Up", type="secondary", use_container_width=True):
                response = requests.post(
                    "http://localhost:8000/auth/register",
                    json={"email": email, "password": password}
                )

                if response.status_code == 201:
                    st.success("Account created! Click Login now.")
                else:
                    error_detail = response.json().get("detail", "Registration failed")
                    st.error(f"Registration failed: {error_detail}")
    else:
        st.info("Enter your email and password above")


# -----------------------
# Upload
# -----------------------
def upload_page():
    st.title("📸 Share Something")

    uploaded_file = st.file_uploader(
        "Choose media",
        type=['png', 'jpg', 'jpeg', 'mp4', 'avi', 'mov', 'mkv', 'webm']
    )

    caption = st.text_area("Caption:", placeholder="What's on your mind?")

    if uploaded_file and st.button("Share", type="primary"):
        with st.spinner("Uploading..."):
            files = {
                "file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)
            }
            data = {"caption": caption}

            response = authorized_request(
                "POST",
                "http://localhost:8000/upload",
                files=files,
                data=data
            )

            if response.status_code == 200:
                st.success("Posted!")
                st.rerun()
            else:
                st.error("Upload failed!")


# -----------------------
# ImageKit helpers
# -----------------------
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

    response = authorized_request("GET", "http://localhost:8000/feed")

    if response.status_code == 200:
        posts = response.json()["posts"]

        if not posts:
            st.info("No posts yet!")
            return

        for post in posts:
            st.markdown("---")

            col1, col2 = st.columns([4, 1])

            with col1:
                st.markdown(f"**{post['email']}** • {post['created_at'][:10]}")

            with col2:
                if post.get('Is Owner', False):
                    if st.button("🗑️", key=f"delete_{post['id']}"):
                        response = authorized_request(
                            "DELETE",
                            f"http://localhost:8000/posts/{post['id']}"
                        )

                        if response.status_code == 200:
                            st.success("Post deleted!")
                            st.rerun()

            caption = post.get('caption', '')

            if post['file_type'] == 'image':
                st.image(create_transformed_url(post['url'], "", caption), width=300)
            else:
                st.video(create_transformed_url(
                    post['url'],
                    "w-400,h-200,cm-pad_resize,bg-blurred"
                ), width=300)
                st.caption(caption)

    else:
        st.error("Failed to load feed")


# -----------------------
# Main
# -----------------------
if st.session_state.user is None:
    login_page()
else:
    st.sidebar.title(f"👋 Hi {st.session_state.user['email']}!")

    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.session_state.token = None
        st.session_state.password = None
        st.rerun()

    st.sidebar.markdown("---")
    page = st.sidebar.radio("Navigate:", ["🏠 Feed", "📸 Upload"])

    if page == "🏠 Feed":
        feed_page()
    else:
        upload_page()