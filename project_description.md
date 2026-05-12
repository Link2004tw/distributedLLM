## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 1

This project is a groupproject, each groupwill be 2 to 5students. Each group will deliver a written
report inadditiontothedevelopedcodebytheend of theproject that shows thedetailedanalysis,
design, testing ... etc. of the project and the description of the used techniques, problem
description, detailed solution, limitations, sample output, references, and any additional
information related to the project. Online Demo (YouTube) Video, presentation, and discussion will
be conducted by the end of the project.

## Introduction

This coursework is itemized into several parts to get the 35 marks associated to it. You
must use the templates provided by the instructor to prepare your work.
All assignments and projects will be handed-in electronically, while quizzes and exams are written .

Learning Outcome to be assessed

- Design a distributed computing model to solve a complex problem
- Design and Implement a distributed computing model
- Configure a working environment for distributed computing
  4 Work and communicate effectively in a team

## Marking Criteria 89%

and above:
Your work must be of outstanding quality and fully meet the requirements of the coursework specification and
learning outcomes stated. You must show independent thinking and apply this to your work showing
originality and consideration of key issues. There must be evidence of wider reading on the subject. In
addition, your proposed solution should:

- illustrate a professional ability of drafting construction details,
- express a deep understanding of the in-hand problem definition,
- and applying, masterly, the learned knowledge in the proposed solution.

## 76% - 89%:

Your work must be of good quality and meet the requirements of the coursework specification and learning
outcomes stated. You must demonstrate some originality in your work and show this by applying new
learning to the key issues of the coursework. There must be evidence of wider reading on the subject. In
addition, your proposed solution should:

- illustrate a Good ability of drafting construction details,
- express a very Good understanding of the in-hand problem definition,
- and applying most of the learned knowledge, correctly, in the proposed solution.

## 67% - 76%:

Your work must be comprehensive and meet all of the requirements stated by the coursework specification

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 2

and learning outcomes. You must show a good understanding of the key concepts and be able to apply them
to solve the problem set by the coursework. There must be enough depth to your work to provide evidence
of wider reading. In addition, your proposed solution should:

- illustrate a moderate ability of drafting construction details,
- express a good understanding of the in-hand problem definition,
- and applying most of the learned knowledge, correctly, in the proposed solution.

## 60%

## -

## 67%

## :

Your work must be of a standard that meets the requirements stated by the coursework specification and
learning outcomes. You must show a reasonable level of understanding of the key concepts and principles
and you must have applied this knowledge to the coursework problem. There should be some evidence of
wider reading. In addition, your proposed solution should:

- illustrate a fair ability of drafting construction details,
- express a fair understanding of the in-hand problem definition,
- and applying some of the learned knowledge, correctly, in the proposed solution.

## B

elow

## 60%

## :

Your work is of poor quality and does not meet the requirements stated by the coursework specification and
learning outcomes. There is a lack of understanding of key concepts and knowledge and no evidence of wider
reading. In addition, your proposed solution would be:

- Illustrate an inability of drafting construction details,
- Failed to define the parameters, limitations, and offerings of the in-hand problem,
- Failed to apply correctly the learned knowledge for proposing a valid solution.

## Academic Misconduct

The University defines Academic Misconduct as ‘any case of deliberate, premeditated cheating, collusion,
plagiarism or falsification of information, in an attempt to deceive and gain an unfair advantage in
assessment’. This includes attempting to gain marks as part of a team without making a contribution. The
department takes Academic Misconduct very seriously and any suspected cases will be investigated through
the University’s standard policy. If you are found guilty, you may be expelled from the University with no
award.
It is your responsibility to ensure that you understand what constitutes Academic Misconduct and to
ensure that you do not break the rules. If you are unclear about what is required, please ask.

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 3

Title: Efficient Load Balancing and GPU Cluster Task Distribution for Handling 1000+
Concurrent LLM Requests

Description: This project aims to design and implement a distributed system capable of
handling 1000+ concurrent user requestsinvolving Large Language Model (LLM)
inference and Retrieval-Augmented Generation (RAG).
The system focuses on efficient load balancing and task distribution across GPU clusters to ensure high
performance, low latency, and optimal resource utilization.
The implementation will simulate real-world AI workloads where requests require heavy computation
and must be distributed dynamically across multiple processing nodes. A key focus will be
on scalability, performance optimization, and fault tolerance in distributed environments.

Features and Specifications:

## ● Load Balancing Mechanism:

The system should distribute incoming user requests efficiently across multiple compute nodes using
strategies such as:

## • Round Robin

## • Least Connections

- Load-aware routing
  ● GPU Cluster Task Distribution:
- Assign LLM inference tasks across multiple GPU nodes
- Optimize GPU utilization and minimize idle time
- Support parallel processing of requests
  ● LLM Inference Handling:
- Process user queries using LLM models
- Handle high concurrency efficiently
  ● RAG Integration:
- Retrieve relevant data from a knowledge base
- Enhance LLM responses with contextual information

## ● Scalability:

- System should handle increasing number of users (up to 1000+)
- Efficient scaling of compute resources

## ● Fault Tolerance:

- Detect node failures
- Reassign tasks automatically
- Maintain system availability

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 4

## User Stories:

● As a user, I want to send multiple AI requests simultaneously and receive fast responses.
● As a user, I want the system to remain responsive even under heavy load.
● As a user, I want the system to continue functioning even if some nodes fail.
● As a user, I want consistent and accurate responses from the LLM system.
● As a system administrator, I want to monitor performance and resource utilization.

## System Architecture:

## ● Client Layer

- Simulates 1000 concurrent users
- Sends requests to the system

## ● Load Balancer

- Receives incoming requests
- Distributes them across compute nodes
- Implements scheduling strategies
  ● Master Node (Controller)
- Manages task scheduling
- Assigns requests to GPU nodes
- Monitors system performance
  ● GPU Worker Nodes
- Execute LLM inference tasks
- Process requests in parallel
- Return results to master node
  ● RAG Module
- Retrieves relevant data
- Enhances LLM responses

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 5

Fault Tolerance Mechanisms to Implement:

## ● Worker Node Failure:

- Detect failed GPU nodes
- Reassign tasks to active nodes

## ● Task Reassignment:

- Ensure no request is lost
- Maintain processing continuity

## ● Load Balancer Resilience:

- Continue distributing requests even under partial failure

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 6

## Technology Suggestions:

## ● Programming Language: Python

● LLM Frameworks:

- PyTorch
- TensorFlow

## ● Load Balancing Tools:

## • NGINX

- HAProxy
  ● GPU Computing:

## • CUDA

- NVIDIA GPU libraries

## ● Data Handling:

- Vector databases (for RAG)

## Implementation Steps:

- System Design and Architecture Definition

## 2. Load Balancer Implementation

- GPU Task Distribution Logic
- LLM Inference Integration
- RAG Pipeline Implementation

## 6. Performance Optimization

## 7. Fault Tolerance Implementation

- Testing and Evaluation

## 9. Documentation

Testing and Evaluation (Focus on Fault Tolerance):

## ● Load Testing:

- Simulate 100 → 1000 concurrent users

## ● Performance Metrics:

## • Latency

## • Throughput

- GPU utilization

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 7

## ● Failure Simulation:

- Shut down nodes during execution
- Verify system recovery

## Project Phases

## Phase 1: Architecture Design

- Define system components
- Design data flow
- Select technologies

## Phase 2: Core Implementation

- Implement load balancing
- Implement GPU task distribution
- Basic LLM inference

## Phase 3: Enhancement & Fault Tolerance

- Add RAG integration
- Implement fault tolerance
- Improve performance

## Phase 4: Testing & Finalization

- Full system testing
- Performance evaluation
- Documentation and presentation

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 8

## Code Skeleton

- Request/Response

- Load Balancer (Round Robin)

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 9

## • Master Scheduler

- GPU Worker Node

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 10

- RAG Retriever (Stub)

- LLM Inference (Stub)

## • Client Load Generator (1000 Users)

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 11

## • Main Entry Point

How to run the above skeleton:

- Install Python 3.9+ and verify with python --version
- Create the project folders (client, master, workers, lb, rag, llm, common)
- Create all required .py files inside each folder
- Copy the provided code into the corresponding files
- Open terminal and navigate to the project root folder
- (Optional) Set PYTHONPATH=. if imports fail
- Run the project using python main.py
- Observe logs showing scheduler, load balancer, and workers processing requests
- Adjust number of users in run_load_test() for load testing
- Adjust number of workers in main.py to simulate more/less GPUs

## Ain Shams University

Faculty of Engineering
CSE354: Distributed Computing – 2
nd

## Semester 2025/2026

## 12
