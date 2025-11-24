from flask import Flask, render_template, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, User, Task

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///task_tracker.db'

db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()


@app.route('/')
def index():
    return redirect('/login')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')

        user = User(email=email, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect('/login')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect('/dashboard')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')


@app.route('/tasks')
@login_required
def tasks():
    from datetime import datetime
    
    # Get filter parameters
    filter_status = request.args.get('status', 'all')
    filter_priority = request.args.get('priority', 'all')
    filter_category = request.args.get('category', 'all')
    search_query = request.args.get('search', '')
    
    # Base query
    query = Task.query.filter_by(user_id=current_user.id)
    
    # Apply filters
    if filter_status == 'completed':
        query = query.filter_by(completed=True)
    elif filter_status == 'pending':
        query = query.filter_by(completed=False)
    
    if filter_priority != 'all':
        query = query.filter_by(priority=filter_priority)
    
    if filter_category != 'all':
        query = query.filter_by(category=filter_category)
    
    if search_query:
        query = query.filter(Task.title.ilike(f'%{search_query}%'))
    
    user_tasks = query.order_by(Task.created_at.desc()).all()
    
    # Get unique categories for filter
    categories = db.session.query(Task.category).filter_by(user_id=current_user.id).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('tasks.html', tasks=user_tasks, categories=categories, today=datetime.now().date())


@app.route('/add-task', methods=['POST'])
@login_required
def add_task():
    from datetime import datetime
    
    title = request.form['title']
    description = request.form.get('description', '')
    priority = request.form.get('priority', 'medium')
    category = request.form.get('category', 'general')
    due_date_str = request.form.get('due_date')
    notes = request.form.get('notes', '')
    
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
        except:
            pass
    
    task = Task(
        title=title,
        description=description,
        priority=priority,
        category=category,
        due_date=due_date,
        notes=notes,
        user_id=current_user.id
    )
    db.session.add(task)
    db.session.commit()
    return redirect('/tasks')


@app.route('/edit-task/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    from datetime import datetime
    
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        return redirect('/tasks')
    
    if request.method == 'POST':
        task.title = request.form['title']
        task.description = request.form.get('description', '')
        task.priority = request.form.get('priority', 'medium')
        task.category = request.form.get('category', 'general')
        task.notes = request.form.get('notes', '')
        
        due_date_str = request.form.get('due_date')
        if due_date_str:
            try:
                task.due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
            except:
                pass
        
        db.session.commit()
        return redirect('/tasks')
    
    return render_template('edit_task.html', task=task)


@app.route('/complete-task/<int:task_id>')
@login_required
def complete_task(task_id):
    task = Task.query.get(task_id)
    if task and task.user_id == current_user.id:
        task.completed = not task.completed
        db.session.commit()
    return redirect(request.referrer or '/tasks')


@app.route('/delete-task/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get(task_id)
    if task and task.user_id == current_user.id:
        db.session.delete(task)
        db.session.commit()
    return redirect(request.referrer or '/tasks')


@app.route('/dashboard')
@login_required
def dashboard():
    from datetime import datetime, timedelta
    
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    total = len(tasks)
    completed = len([t for t in tasks if t.completed])
    pending = total - completed
    
    # Completion rate
    completion_rate = round((completed / total * 100), 1) if total > 0 else 0
    
    # Priority breakdown
    high_priority = len([t for t in tasks if t.priority == 'high' and not t.completed])
    medium_priority = len([t for t in tasks if t.priority == 'medium' and not t.completed])
    low_priority = len([t for t in tasks if t.priority == 'low' and not t.completed])
    
    # Category breakdown
    categories = {}
    for task in tasks:
        if task.category not in categories:
            categories[task.category] = {'total': 0, 'completed': 0}
        categories[task.category]['total'] += 1
        if task.completed:
            categories[task.category]['completed'] += 1
    
    # Overdue tasks
    today = datetime.now()
    overdue = len([t for t in tasks if t.due_date and t.due_date < today and not t.completed])
    
    # Due soon (next 3 days)
    due_soon = len([t for t in tasks if t.due_date and t.due_date > today and t.due_date < today + timedelta(days=3) and not t.completed])
    
    # Recent tasks (last 5)
    recent_tasks = sorted(tasks, key=lambda x: x.created_at, reverse=True)[:5]
    
    # Productivity score
    productivity_score = min(100, int(completion_rate * 1.2)) if total > 0 else 0
    if overdue > 0:
        productivity_score = max(0, productivity_score - (overdue * 5))
    
    # Streak calculation (simplified)
    streak_days = completed // 3 if completed > 0 else 0
    
    return render_template(
        'dashboard.html',
        total=total,
        completed=completed,
        pending=pending,
        completion_rate=completion_rate,
        high_priority=high_priority,
        medium_priority=medium_priority,
        low_priority=low_priority,
        categories=categories,
        overdue=overdue,
        due_soon=due_soon,
        recent_tasks=recent_tasks,
        productivity_score=productivity_score,
        streak_days=streak_days
    )


if __name__ == '__main__':
    app.run(debug=True)
