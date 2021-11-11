'''
This was yoinked from
https://developer.algorand.org/docs/get-details/dapps/pyteal/
we will probably need to make a couple of adjustments...just palced raw copy pasta for now
'''

import base64

from algosdk.future import transaction
from algosdk import account, mnemonic, logic
from algosdk.v2client import algod
from pyteal import *

tmpl_timeout= Int(17826590)
tmpl_fee = Int(1000)
tmpl_period = Int(1) 
tmpl_dur = Int(1) # Since this would be a One time transaction after timeout 
tmpl_lease = Bytes("base64", "023sdDE2")
tmpl_amt = Int(2000)
tmpl_rcv = Addr("YDUVA6WMJAFVOF5GEVHGHHTMMKOE5MCVS6OIDZ4S5XKLQPCEZ3ZB7URJQ4") #Reciever address
tmpl_timeout = Int(30000) 

# user declared account mnemonics
creator_mnemonic = "allow artist school host piano six gravity music sail success fancy accuse ginger blouse tired cherry awesome frozen absorb bike cheese speed castle ability chronic"
# user declared algod connection parameters. Node must have EnableDeveloperAPI set to true in its config
algod_token = "267962e2624ed5c1d4bf8a2ea638fc455812087b288eb044dc6f3a671645310a"
algod_address = "http://127.0.0.1:8080"

# helper function to compile program source
def compile_program(client, source_code):
    compile_response = client.compile(source_code)
    return base64.b64decode(compile_response['result'])

# helper function that converts a mnemonic passphrase into a private signing key
def get_private_key_from_mnemonic(mn) :
    private_key = mnemonic.to_private_key(mn)
    return private_key

# helper function that waits for a given txid to be confirmed by the network
def wait_for_confirmation(client, transaction_id, timeout):
    """
    Wait until the transaction is confirmed or rejected, or until 'timeout'
    number of rounds have passed.
    Args:
        transaction_id (str): the transaction to wait for
        timeout (int): maximum number of rounds to wait
    Returns:
        dict: pending transaction information, or throws an error if the transaction
            is not confirmed or rejected in the next timeout rounds
    """
    start_round = client.status()["last-round"] + 1
    current_round = start_round

    while current_round < start_round + timeout:
        try:
            pending_txn = client.pending_transaction_info(transaction_id)
        except Exception:
            return
        if pending_txn.get("confirmed-round", 0) > 0:
            return pending_txn
        elif pending_txn["pool-error"]:
            raise Exception(
                'pool error: {}'.format(pending_txn["pool-error"]))
        client.status_after_block(current_round)
        current_round += 1
    raise Exception(
        'pending tx not found in timeout rounds, timeout value = : {}'.format(timeout))

# helper function that formats global state for printing
def format_state(state):
    formatted = {}
    for item in state:
        key = item['key']
        value = item['value']
        formatted_key = base64.b64decode(key).decode('utf-8')
        if value['type'] == 1:
            # byte string
            if formatted_key == 'voted':
                formatted_value = base64.b64decode(value['bytes']).decode('utf-8')
            else:
                formatted_value = value['bytes']
            formatted[formatted_key] = formatted_value
        else:
            # integer
            formatted[formatted_key] = value['uint']
    return formatted

# helper function to read app global state
def read_global_state(client, addr, app_id):
    results = client.account_info(addr)
    apps_created = results['created-apps']
    for app in apps_created:
        if app['id'] == app_id:
            return format_state(app['params']['global-state'])
    return {}


"""Basic Counter Application in PyTeal"""

def approval_program():
    on_creation = Seq([
        App.globalPut(Bytes("Count"), Int(0)),
        Return(Int(1))
    ])

    handle_optin = Return(Int(0))

    handle_closeout = Return(Int(0))

    handle_updateapp = Return(Int(0))

    handle_deleteapp = Return(Int(0))

    scratchCount = ScratchVar(TealType.uint64)

    add = Seq([
        scratchCount.store(App.globalGet(Bytes("Count"))),
        App.globalPut(Bytes("Count"), scratchCount.load() + Int(1)),
        Return(Int(1))
    ])

    deduct = Seq([
       scratchCount.store(App.globalGet(Bytes("Count"))),
        If(scratchCount.load() > Int(0),
            App.globalPut(Bytes("Count"), scratchCount.load() - Int(1)),
        ),
        Return(Int(1))
   ])

    handle_noop = Cond(
        [And(
            Global.group_size() == Int(1),
            Txn.application_args[0] == Bytes("Add")
        ), add],
        [And(
            Global.group_size() == Int(1),
            Txn.application_args[0] == Bytes("Deduct")
        ), deduct],
    )

    program = Cond(
        [Txn.application_id() == Int(0), on_creation],
        [Txn.on_completion() == OnComplete.OptIn, handle_optin],
        [Txn.on_completion() == OnComplete.CloseOut, handle_closeout],
        [Txn.on_completion() == OnComplete.UpdateApplication, handle_updateapp],
        [Txn.on_completion() == OnComplete.DeleteApplication, handle_deleteapp],
        [Txn.on_completion() == OnComplete.NoOp, handle_noop]
    )
    # Mode.Application specifies that this is a smart contract
    return compileTeal(program, Mode.Application, version=3)

def smart_contract_program(tmpl_fee=tmpl_fee,tmpl_period=tmpl_period,tmpl_dur=tmpl_dur,tmpl_lease=tmpl_lease,tmpl_amt=tmpl_amt,tmpl_rcv=tmpl_rcv,tmpl_timeout=tmpl_timeout):
	periodic_pay_core = And(Txn.type_enum() == TxnType.Payment,Txn.fee() < tmpl_fee,Txn.first_valid() % tmpl_period == Int(0),Txn.last_valid() == tmpl_dur + Txn.first_valid(),Txn.lease() == tmpl_lease)
	periodic_pay_close = And(Txn.close_remainder_to() == tmpl_rcv,Txn.rekey_to() == tmpl_rcv,Txn.receiver() == tmpl_rcv,Txn.first_valid() == tmpl_timeout,Txn.amount() == tmpl_amt,)
	periodic_pay_escrow = periodic_pay_core.And(periodic_pay_close)
   	return compileTeal(periodic_pay_escrow, Mode.Application, version=3)#

def clear_state_program():
    program = Return(Int(1))
    # Mode.Application specifies that this is a smart contract
    return compileTeal(program, Mode.Application, version=3)


# create new application
def create_app(client, private_key, approval_program, clear_program, global_schema, local_schema):
    # define sender as creator
    sender = account.address_from_private_key(private_key)

    # declare on_complete as NoOp
    on_complete = transaction.OnComplete.NoOpOC.real

    # get node suggested parameters
    params = client.suggested_params()

    # create unsigned transaction
    txn = transaction.ApplicationCreateTxn(sender, params, on_complete, \
                                            approval_program, clear_program, \
                                            global_schema, local_schema)

    # sign transaction
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    # send transaction
    client.send_transactions([signed_txn])

    # await confirmation
    wait_for_confirmation(client, tx_id, 5)

    # display results
    transaction_response = client.pending_transaction_info(tx_id)
    app_id = transaction_response['application-index']
    print("Created new app-id:", app_id)

    return app_id


# call application
def call_app(client, private_key, index, app_args) :
    # declare sender
    sender = account.address_from_private_key(private_key)

    # get node suggested parameters
    params = client.suggested_params()

    # create unsigned transaction
    txn = transaction.ApplicationNoOpTxn(sender, params, index, app_args)

    # sign transaction
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    # send transaction
    client.send_transactions([signed_txn])

    # await confirmation
    wait_for_confirmation(client, tx_id, 5)

    print("Application called")


def main() :
    # initialize an algodClient
    algod_client = algod.AlgodClient(algod_token, algod_address)

    # define private keys
    creator_private_key = get_private_key_from_mnemonic(creator_mnemonic)

    # declare application state storage (immutable)
    local_ints = 0
    local_bytes = 0
    global_ints = 1
    global_bytes = 0
    global_schema = transaction.StateSchema(global_ints, global_bytes)
    local_schema = transaction.StateSchema(local_ints, local_bytes)

    # compile program to TEAL assembly
    with open("./approval.teal", "w") as f:
        approval_program_teal = approval_program()
        f.write(approval_program_teal)
    
    with open("./smart_contract.teal", "w") as f: #Write smart contract teal to file
        smart_contract_teal = smart_contract_program()
        f.write(smart_contract_teal)

    # compile program to TEAL assembly
    with open("./clear.teal", "w") as f:
        clear_state_program_teal = clear_state_program()
        f.write(clear_state_program_teal)

    # compile program to binary
    approval_program_compiled = compile_program(algod_client, approval_program_teal)
    smart_contract_compiled = compile_program(algod_client, smart_contract_teal)# Added - Compile smart program

    # compile program to binary
    clear_state_program_compiled = compile_program(algod_client, clear_state_program_teal)

    print("--------------------------------------------")
    print("Deploying Counter application......")

    # create new application
    app_id = create_app(algod_client, creator_private_key, approval_program_compiled, clear_state_program_compiled, global_schema, local_schema) #Replace approval_program_compiled with Smart contract compiled. 

    # read global state of application
    print("Global state:", read_global_state(algod_client, account.address_from_private_key(creator_private_key), app_id))

    print("--------------------------------------------")
    print("Calling Counter application......")
    app_args = ["Add"]
    call_app(algod_client, creator_private_key, app_id, app_args)

    # read global state of application
    print("Global state:", read_global_state(algod_client, account.address_from_private_key(creator_private_key), app_id))

main()
