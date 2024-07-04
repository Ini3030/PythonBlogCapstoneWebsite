from dataclasses import dataclass
from datetime import date, datetime
import os
import random
import secrets

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Integer, String, Text, orm
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import generate_password_hash, check_password_hash
import nh3

from forms import PostForm, RegisterForm, LoginForm, CommentForm


# Load the .env file
load_dotenv()


app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex()
login_manager = LoginManager()
login_manager.init_app(app)
ckeditor = CKEditor(app)  # Initiates CKEditor fields for the blog
Bootstrap5(app)  # initiates Bootstrap5


# CREATE DATABASE
class Base(DeclarativeBase):
    pass


app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SQLALCHEMY_DATABASE_URI")
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES — One-to-many bidirectional relationships
@dataclass
class User(db.Model, UserMixin):
    __tablename__ = "user_table"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(500), unique=True)
    # Parent relationship with BlogPost table:
    posts = relationship("BlogPost", back_populates="author")
    # Parent relationship with Comment table:
    comments = relationship("Comment", back_populates="comment_author")


@dataclass
class BlogPost(db.Model):
    __tablename__ = "post_table"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    # Child relationship with User table:
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("user_table.id"))
    author = relationship("User", back_populates="posts")
    # Parent relationship with Comment table:
    post_comments = relationship("Comment", back_populates="parent_post")


@dataclass
class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Child relationship with User table:
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("user_table.id"))
    comment_author = relationship("User", back_populates="comments")
    # Child relationship with BlogPost table:
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("post_table.id"))
    parent_post = relationship("BlogPost", back_populates="post_comments")


with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ----------------------------------------------------ROUTES-----------------------------------------------------------


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email_exist = User.query.filter_by(email=form.email.data).first()
        username_exist = User.query.filter_by(name=form.name.data).first()
        if not email_exist and not username_exist:
            random_salt_len: int = random.randint(16, 32)
            # noinspection PyTypeChecker
            new_user = User(email=form.email.data,
                            password=generate_password_hash(password=form.password.data,
                                                            method="pbkdf2:sha256",
                                                            salt_length=random_salt_len),
                            name=form.name.data,)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            flash("Registered successfully.", "info")
            return redirect(url_for("get_all_posts"))
        else:
            flash("That email or username are already in use.", "info")
            return render_template("register.html", form=form)
    return render_template("register.html", form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user_exist = User.query.filter_by(email=form.email.data).first()
        except orm.exc.NoResultFound:
            # SQLAlchemy.orm exception
            flash("Incorrect password or email, please try again.", "info")
            print(f"SQLAlchemy.orm exception: User {form.email.data} not found!")
            return render_template("login.html", form=form)
        if user_exist:
            if check_password_hash(pwhash=user_exist.password, password=form.password.data):
                login_user(user_exist)
                flash("Logged in successfully.", "info")
                return redirect(url_for("get_all_posts"))
            else:
                flash("Incorrect password or email, please try again.", "info")
                return render_template("login.html", form=form)
        else:
            flash("Incorrect password or email, please try again.", "info")
            return render_template("login.html", form=form)
    return render_template("login.html", form=form)


@app.route('/logout')
def logout():
    if current_user.is_anonymous:
        flash("You're not currently logged in to an account.", "info")
    else:
        logout_user()
        flash("Logged out successfully.", "info")
    return redirect(url_for('get_all_posts'))


# TODO: Use a decorator so only an admin user can create a new post
@app.route('/')
def get_all_posts():
    # Query the database for all the posts. Convert the data to a python list.
    all_posts = BlogPost.query.order_by(BlogPost.id.desc()).all()
    posts = [post for post in all_posts]
    return render_template("index.html", all_posts=posts)


# Route so that you can click on individual posts.
@app.route('/<post_id>', methods=["GET", "POST"])
def show_post(post_id):
    # Retrieve a BlogPost from the database based on the post_id
    requested_post = db.get_or_404(BlogPost, post_id)
    # Comment section:
    form = CommentForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.", "info")
            return redirect(url_for("login"))
        # noinspection PyArgumentList
        new_comment = Comment(text=nh3.clean(form.comment.data),
                              date=datetime.now().strftime("%B %d, %Y, %I:%M%p"),
                              comment_author=current_user,
                              parent_post=requested_post,
                              )
        db.session.add(new_comment)
        db.session.commit()
        form.comment.data = ""
        return redirect(url_for('show_post', post_id=post_id))
    return render_template("post.html", post=requested_post, form=form)


# add_new_post() to create a new blog post
@app.route("/new-post", methods=["GET", "POST"])
def add_new_post():
    if current_user.is_authenticated:
        form = PostForm()
        if form.validate_on_submit():
            # noinspection PyTypeChecker,PyArgumentList
            new_post = BlogPost(
                title=form.title.data,
                subtitle=form.subtitle.data,
                body=nh3.clean(form.body.data),
                img_url=form.img_url.data,
                author=current_user,
                date=date.today().strftime("%B %d, %Y"),
            )
            db.session.add(new_post)
            db.session.commit()
            return redirect(url_for("get_all_posts"))
        return render_template("make-post.html", form=form)
    else:
        flash("You must be logged in to submit a new post.", "info")
        return redirect(url_for("get_all_posts"))


@app.route("/edit/<post_id>", methods=["GET", "POST"])
def edit_post(post_id):
    post_to_edit = db.get_or_404(BlogPost, post_id)
    # Auto-completed form
    if not current_user.is_anonymous:
        if current_user == post_to_edit.author:
            form = PostForm(
                title=post_to_edit.title,
                subtitle=post_to_edit.subtitle,
                img_url=post_to_edit.img_url,
                body=post_to_edit.body,
            )
            if form.validate_on_submit():
                post_to_edit.title = form.title.data
                post_to_edit.subtitle = form.subtitle.data
                post_to_edit.img_url = form.img_url.data
                post_to_edit.body = nh3.clean(form.body.data)
                db.session.commit()
                return redirect(url_for("show_post", post_id=post_to_edit.id))
            return render_template("make-post.html", form=form, is_edit=True)
        else:
            flash("You do not have permissions to complete that action.", "info")
            return redirect(url_for("get_all_posts"))
    else:
        flash("You must be logged in to complete actions.", "info")
        return redirect(url_for("get_all_posts"))


@app.route("/delete/<post_id>")
def delete_post(post_id):
    dead_post = db.get_or_404(BlogPost, post_id)
    if not current_user.is_anonymous:
        if current_user == dead_post.author:
            db.session.delete(dead_post)
            db.session.commit()
            return redirect(url_for("get_all_posts"))
        else:
            flash("You do not have permissions to complete that action.", "info")
            return redirect(url_for("get_all_posts"))
    else:
        flash("You must be logged in to complete actions.", "info")
        return redirect(url_for("get_all_posts"))


@app.route("/user-posts/<author_name>")
def show_user_posts(author_name):
    user = User.query.filter_by(name=author_name).first()
    author_posts = BlogPost.query.filter_by(author_id=user.id).all()
    posts = reversed([post for post in author_posts])
    return render_template("user_posts.html", author_posts=posts, author_name=author_name)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


if __name__ == "__main__":
    debug = bool(os.getenv("DEBUG"))
    app.run(debug=debug, port=5003)


# TODO: add admin powers
# TODO: create signature decorator for delete/edit
# TODO: integrate Gravatar (https://www.udemy.com/course/100-days-of-code/learn/lecture/22907196#questions/21081802)
# TODO: allow deletion of comments (and edition maybe)
