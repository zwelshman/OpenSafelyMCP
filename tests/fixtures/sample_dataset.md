# Dataset definition

This page describes how to define a dataset in ehrQL.

## Creating variables

Use `create_dataset` to define your dataset.

```python
from ehrql import create_dataset
dataset = create_dataset()
```

## Filtering patients

Filter patients using the `where` method.

```python
dataset = dataset.where(age >= 18)
```

## Dummy data generation

Generate dummy data for testing your study definition.
