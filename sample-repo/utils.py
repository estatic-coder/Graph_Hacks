def format_user_data(user_row):
    if not user_row:
        return None
    return {"id": user_row[0], "name": user_row[1]}
