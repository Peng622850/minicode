import json

# Read data from data.json
with open('data.json', 'r') as file:
    data = json.load(file)

# Print the contents
print("Contents of data.json:")
print(data)

# Print individual fields
print("\nIndividual Details:")
print(f"Name: {data['name']}")
print(f"Age: {data['age']}")
print(f"City: {data['city']}")