from django.shortcuts import render
from django.http import HttpResponseRedirect
# <HINT> Import any new Models here
from .models import Course, Enrollment, Question, Choice, Submission
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
import logging
# Get an instance of a logger
logger = logging.getLogger(__name__)
# Create your views here.


def registration_request(request):
    context = {}
    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)
    elif request.method == 'POST':
        # Check if user exists
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']
        user_exist = False
        try:
            User.objects.get(username=username)
            user_exist = True
        except:
            logger.error("New user")
        if not user_exist:
            user = User.objects.create_user(username=username, first_name=first_name, last_name=last_name,
                                            password=password)
            login(request, user)
            return redirect("onlinecourse:index")
        else:
            context['message'] = "User already exists."
            return render(request, 'onlinecourse/user_registration_bootstrap.html', context)


def login_request(request):
    context = {}
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')
        else:
            context['message'] = "Invalid username or password."
            return render(request, 'onlinecourse/user_login_bootstrap.html', context)
    else:
        return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    is_enrolled = False
    if user.id is not None:
        # Check if user enrolled
        num_results = Enrollment.objects.filter(user=user, course=course).count()
        if num_results > 0:
            is_enrolled = True
    return is_enrolled


# CourseListView
class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]
        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)
        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)
    if not is_enrolled and user.is_authenticated:
        # Create an enrollment
        Enrollment.objects.create(user=user, course=course, mode='honor')
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(reverse(viewname='onlinecourse:course_details', args=(course.id,)))


def extract_answers(request):
   submitted_anwsers = []
   for key in request.POST:
       if key.startswith('choice'):
           value = request.POST[key]
           choice_id = int(value)
           submitted_anwsers.append(choice_id)
   return submitted_anwsers




def submit(request, course_id):
    if request.method != "POST":
        return redirect("onlinecourse:course_details", pk=course_id)

    course = get_object_or_404(Course, pk=course_id)

    if not request.user.is_authenticated:
        return redirect("onlinecourse:login")

    enrollment = Enrollment.objects.filter(
        user=request.user, course=course
    ).first()

    if enrollment is None:
        enrollment = Enrollment.objects.create(
            user=request.user, course=course, mode="honor"
        )

    submission = Submission.objects.create(enrollment=enrollment)

    selected_ids = []
    for key, value in request.POST.items():
        if key.startswith("choice"):
            try:
                selected_ids.append(int(value))
            except (TypeError, ValueError):
                continue

    valid_choices = Choice.objects.filter(
        question__course=course, id__in=selected_ids
    )
    submission.choices.set(valid_choices)

    return redirect(
        "onlinecourse:show_exam_result",
        course_id=course.id,
        submission_id=submission.id,
    )

def show_exam_result(request, course_id, submission_id):
    from django.http import HttpResponseForbidden

    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
    )

    if (
        request.user.is_authenticated
        and submission.enrollment.user != request.user
    ):
        return HttpResponseForbidden(
            "You cannot view another learner's result."
        )

    questions = Question.objects.filter(
        course=course
    ).prefetch_related("choices")

    selected_ids = set(
        submission.choices.values_list("id", flat=True)
    )

    results = []
    total_score = 0
    possible_score = 0

    for question in questions:
        question_choices = list(question.choices.all())
        selected_choices = [
            choice for choice in question_choices
            if choice.id in selected_ids
        ]
        correct_choices = [
            choice for choice in question_choices
            if choice.is_correct
        ]

        is_correct = question.is_get_score(
            [choice.id for choice in selected_choices]
        )

        possible_score += question.grade
        if is_correct:
            total_score += question.grade

        results.append({
            "question": question,
            "choices": question_choices,
            "selected_choices": selected_choices,
            "correct_choices": correct_choices,
            "is_correct": is_correct,
        })

    correct_count = sum(
        1 for result in results if result["is_correct"]
    )
    total_questions = len(results)

    grade = (
        round(total_score * 100 / possible_score)
        if possible_score > 0 else 0
    )

    return render(
        request,
        "onlinecourse/exam_result_bootstrap.html",
        {
            "course": course,
            "submission": submission,
            "results": results,
            "grade": grade,
            "correct_count": correct_count,
            "total_questions": total_questions,
            "total_score": total_score,
            "possible_score": possible_score,
        },
    )
