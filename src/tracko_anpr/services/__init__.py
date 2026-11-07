"""The service layer: what the application can do, independent of how it is asked.

The API routes (`tracko_anpr.api`) and the dashboard pages (`tracko_anpr.dashboard`) both call
these functions with a database session, so the dashboard could later move to its own process
and talk to the API without any logic changing hands. Services return plain dataclasses, which
FastAPI serialises as they are.

Nothing here runs the models: processing is queued for the worker (`tracko_anpr.worker`).
"""
