"""Grade evidence shared by the natural-confirmation producer and reader."""


def grade_evidence(proposal_valid, timely, applied, exits, required, confirmed):
    if (confirmed or proposal_valid is False or timely is False or applied is False
            or any(value is not None and value != 0 for value in exits.values())):
        return "failed"
    if (proposal_valid is not True or timely is not True or applied is not True
            or not required <= exits.keys() or any(exits[k] is None for k in required)):
        return "pending"
    return "pass"
