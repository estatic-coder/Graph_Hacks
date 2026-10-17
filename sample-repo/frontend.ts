async function fetchUser(userId: number) {
    const response = await fetch(`/users/${userId}`);
    return response.json();
}
