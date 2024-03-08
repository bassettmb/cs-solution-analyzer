import os
import subprocess

from .get_args import get_args
from ..lib.solution import Solution


def main():
    config = get_args()
    solution = Solution(config.solution)
    for project in solution.projects():
        print(project.project_id.path)

if __name__ == "__main__":
    main()
