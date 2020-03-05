import logging
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1] / 'jambot'))

import azure.functions as func

import functions as f
import livetrading as live

def err():
    return func.HttpResponse('ERROR: Http function not triggered.', status_code=400)

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        action = req.params.get('action')
        if not action:
            try:
                req_body = req.get_json()
            except:
                return err()
            else:
                action = req_body.get('action')

        if action == 'refresh_balance':
            live.refresh_gsheet_balance()
            return func.HttpResponse('refresh balance success', status_code=200)
        elif action == 'run_toploop':
            live.TopLoop(partial=True)
            return func.HttpResponse('run TopLoop success', status_code=200)
        else:
            return err()
    except:
        try:
            f.senderror()
            return err()
        except:
            return err()
        