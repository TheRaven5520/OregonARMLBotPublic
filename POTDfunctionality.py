from discordHelper import *
import random

helper = discordHelper(None, None)

class Person:
    def __init__(self, person_id, num_attempts=0, grade='0', responses=[]):
        self.num_attempts = num_attempts
        self.grade = grade
        self.id = person_id
        self.responses = responses[:]

    def to_load(self):
        return {'id': self.id, 'num_attempts': self.num_attempts, 'grade': self.grade, 'responses': self.responses}

class Problem:
    g_problem_id = 0
    
    def __init__(self, problem_text: str, answer: str, start_time: str, end_time: str, season_id: str, problem_id=None):
        # set variables
        self.id = problem_id
        if self.id == None:
            Problem.g_problem_id += 1
            self.id = Problem.g_problem_id
        Problem.g_problem_id = max(Problem.g_problem_id, int(self.id))
        self.id = str(self.id)

        self.problem_text = str(problem_text)
        self.answer = str(answer)
        self.start_time = start_time
        self.end_time = end_time
        self.season_id = season_id

        self.persons = {}

    ############### helpers

    def in_interval(self):
        return pd.Timestamp(self.start_time, tz=timezone) <= pd.Timestamp.now(tz=timezone) and \
               pd.Timestamp(self.end_time, tz=timezone) >= pd.Timestamp.now(tz=timezone)

    ############### ACCESSORS

    def get_person(self, person_id: str):
        if person_id in self.persons: return self.persons[person_id]
        return None

    ############### MUTATORS

    def set_person(self, person_id: str, num_attempts: int = 0, grade: float = 0, responses: list = []):
        if person_id in self.persons:
            return False, f"Person with id {person_id} already in problem {self.id}.", None
        self.persons[person_id] = Person(person_id, num_attempts, grade, responses)
        return True, f"Person with id {person_id} added to problem {self.id}.", self.persons[person_id]

    def set_attempts(self, person_id: str, num_attempts: int = 1, add: bool = False):
        person = self.get_person(person_id)
        if not person:
            return False, f"Person {person_id} not found.", None
        if add:
            person.num_attempts += num_attempts
        else:
            person.num_attempts = num_attempts
        return True, f"Person {person_id}'s attempts updated to {person.num_attempts}.", person
        
    def set_grade(self, person_id: str, grade: float, max_out: bool = True):
        person = self.get_person(person_id)
        if not person:
            return False, f"Person {person_id} not found.", None
        res = person.grade != grade 
        person.grade = max(person.grade, grade) if max_out else grade
        return res, f"Person {person_id}'s grade updated to {person.grade}.", person

    def set_ans(self, answer: str):
        self.answer = answer
        return True, f"Answer set successfully."
    
    def set_season(self, season_id: str):
        self.season_id = season_id
        return True, f"Season ID set successfully."

    ############### SCORES

    def solve_scores(self):
        NUM_SOLVES = sum(max(0, min(person.grade, 1)) for person_id, person in self.persons.items())
        scores = []
        
        if NUM_SOLVES > 0:
            solve_score = 100 / NUM_SOLVES
            for person_id, person in self.persons.items():
                if person.grade > 0:
                    score = person.grade * (10 + solve_score / person.num_attempts)
                    scores.append((person.id, score))
        
        return scores

    ################ LOADING

    def to_load(self):
        return {
            'problem_text': self.problem_text, 
            'answer': self.answer, 
            'start_time': self.start_time, 
            'end_time': self.end_time, 
            'season_id': self.season_id, 
            'id': self.id, 
            'persons': [person.to_load() for person_id, person in self.persons.items()]
        }

    def from_load(self, load):
        for person in load:
            self.set_person(person['id'], person['num_attempts'], person['grade'], person['responses'])

class Season:
    def __init__(self):
        self.ungraded_answers = []
        self.problems = {}
        self.CURRENT_SEASON = 0

    ################ ACCESSORS

    def get_problem(self, problem_id: str):
        if problem_id in self.problems: return self.problems[problem_id]
        return None

    def get_last_ungraded(self, gnext = False):
        if self.ungraded_answers:
            if gnext:
                self.ungraded_answers = self.ungraded_answers[1:] + self.ungraded_answers[:1]
            return True, self.ungraded_answers[0]
        else: 
            return False, None
    
    ################ PROBLEM MUTATORS

    def add_problem(self, problem_text: str, answer: str, start_time: str, end_time: str, season_id: str="None"):
        if season_id == "None": season_id = str(self.CURRENT_SEASON)
        problem = Problem(problem_text, answer, start_time, end_time, season_id)
        self.problems[problem.id] = problem 
        return True, f"Problem added successfully", problem

    def delete_problem(self, problem_id: str):
        res = self.problems.pop(problem_id, None)
        res = (res == None)
        text = f"Problem {problem_id} " + ("not found." if res else "deleted.")
        return res, text

    def add_answer(self, problem_id: str, person_id: str, answer: str, filename: str = None):
        problem = self.get_problem(problem_id)
        if not problem: return False, f"Problem {problem_id} not found."
        if not problem.in_interval(): return False, "Not in correct time interval."

        self.ungraded_answers.append({
            'problem_id': problem_id, 
            'person_id': person_id, 
            'answer': answer,
            'filename': filename
        })
        return True, "Answer added."

    def set_answer(self, problem_id: str, answer: str):
        problem = self.get_problem(problem_id)
        if not problem: return False, f"Problem {problem_id} not found."
        result, text = problem.set_ans(answer)
        people_updated = []
        if helper.parse_type(float, answer) is not None:
            for person_id, person in problem.persons.items():
                correct_answer = any(float(response) == float(answer) for response in person.responses)
                [people_updated.append((person_id, correct_answer)) for res, _, _ in [problem.set_grade(person_id, 1 if correct_answer else 0, False)] if res]
        return result, text, people_updated
    
    def set_time(self, problem_id: str, start_time: str, end_time: str):
        problem = self.get_problem(problem_id)
        if not problem: return False, f"Problem {problem_id} not found."
        problem.start_time = start_time
        problem.end_time = end_time
        return True, f"Time set successfully."

    def set_season(self, problem_id: str, season_id: str):
        problem = self.get_problem(problem_id)
        if not problem: return False, f"Problem {problem_id} not found."
        result, text = problem.set_season(season_id)
        return result, text

    ################ PERSON MUTATORS 

    def set_attempts(self, problem_id: str, person_id: str, num_attempts: int):
        problem = self.get_problem(problem_id)
        if not problem: return False, f"Problem {problem_id} not found.", None

        result, text, person = problem.set_attempts(person_id, num_attempts, True)
        if not result:
            result, text, person = problem.set_person(person_id, num_attempts, 0)

        return result, text, person
    
    def set_grade(self, problem_id: str, person_id: str, grade: float, max_out: bool = False):
        problem = self.get_problem(problem_id)
        if not problem: return False, f"Problem {problem_id} not found.", None

        result, text, person = problem.set_grade(person_id, grade, max_out)
        if not result:
            result, text, person = problem.set_person(person_id, 1, grade)

        return result, text, person

    ################ GRADING

    def grade_answer(self, problem_id: str, person_id: str, grade: float, attempts_to_update: int = 1):
        problem = self.get_problem(problem_id)
        if not problem: return False, f"Problem {problem_id} not found."

        person = problem.get_person(person_id)
        if not person:
            problem.set_person(person_id, max(1, attempts_to_update), grade)
        else:
            person.num_attempts += attempts_to_update
            person.grade = max(person.grade, grade)

        return True, "Answer graded successfully."

    def grade_last(self, grade: float, attempts_to_update: int = 1):
        result, last = self.get_last_ungraded()
        if not result: return False, "No ungraded answers."

        result, text = self.grade_answer(last['problem_id'], last['person_id'], grade, attempts_to_update)
        if self.ungraded_answers[0]["filename"]:
            os.remove(f"{DATA_DIR}images/{self.ungraded_answers[0]['filename']}")
        self.ungraded_answers = self.ungraded_answers[1:]
        return result, text

    ################ LOAD

    
    def to_load(self):
        return [problem.to_load() for problem_id, problem in self.problems.items()]
    
    def from_load(self, load):
        for problem in load:
            self.problems[problem['id']] = Problem(problem['problem_text'], problem['answer'], problem['start_time'], problem['end_time'], problem['season_id'], problem['id'])
            self.problems[problem['id']].from_load(problem['persons'])

    ################ GRADING 

    def get_grades(self, season_id: str):
        scores = {}
        for problem_id, problem in self.problems.items():
            if problem.season_id != season_id:
                continue
            new_scores = problem.solve_scores()
            for a, b in new_scores:
                scores[a] = scores.get(a, 0) + b
        return scores 

class Driver:
    def __init__(self):
        self.season = Season()
        self.scheduled_messages = {}
    
    def add_scheduled_message(self, message):
        self.scheduled_messages[str(unique_id())] = message

    def create_season(self, val=1):
        self.season.CURRENT_SEASON += val

    def store_data(self):
        with open(f'{DATA_DIR}data/data.json', 'w') as file:
            json.dump(self.season.to_load(), file, indent=4)

        with open(f'{DATA_DIR}data/ungraded.json', 'w') as file:
            json.dump(self.season.ungraded_answers, file, indent=4)

        with open(f'{DATA_DIR}data/scheduled_messages.json', 'w') as file:
            json.dump(self.scheduled_messages, file, indent=4)

    def load_data(self):
        with open(f'{DATA_DIR}data/data.json', 'r') as file:
            self.season.from_load(json.load(file))

        with open(f'{DATA_DIR}data/ungraded.json', 'r') as file:
            self.season.ungraded_answers = json.load(file)

        with open(f'{DATA_DIR}data/scheduled_messages.json', 'r') as file:
            self.scheduled_messages = json.load(file)

    
    