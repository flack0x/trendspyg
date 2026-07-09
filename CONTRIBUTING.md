# Contributing to trendspyg

Thank you for your interest in contributing to trendspyg! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for all contributors.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue with:
- A clear, descriptive title
- Steps to reproduce the issue
- Expected vs actual behavior
- Your environment (Python version, OS)
- Code samples if applicable

### Suggesting Enhancements

Feature requests are welcome! Please open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Why this would be useful to other users

### Pull Requests

1. **Fork the repository** and create a new branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes:**
   - Write clear, commented code
   - Follow existing code style (PEP 8)
   - Add type hints to all functions
   - Update documentation if needed

3. **Add tests:**
   - All new features must include tests
   - Ensure existing tests still pass
   - Aim for >90% code coverage on new code
   - Every module must stay at or above 80% coverage on its own — CI enforces this
     (`python scripts/check_coverage_floor.py` after a coverage run with `--cov-report=json`)
   ```bash
   pytest tests/ -v --cov=trendspyg
   ```

4. **Update documentation:**
   - Update README.md if adding features
   - Add docstrings to new functions
   - Update CHANGELOG.md

5. **Commit your changes:**
   - Use clear, descriptive commit messages
   - Follow conventional commit format:
     - `feat:` for new features
     - `fix:` for bug fixes
     - `docs:` for documentation
     - `test:` for tests
     - `refactor:` for code refactoring

6. **Push and create a Pull Request:**
   ```bash
   git push origin feature/your-feature-name
   ```
   - Provide a clear PR description
   - Link any related issues
   - Wait for review and feedback

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/flack0x/trendspyg.git
   cd trendspyg
   ```

2. **Install development dependencies:**
   ```bash
   pip install -e .[dev,analysis]
   ```

3. **Run tests:**
   ```bash
   pytest tests/ -v
   ```

4. **Run linting:**
   ```bash
   flake8 trendspyg/
   mypy trendspyg/
   ```

## Code Style

- Follow PEP 8 guidelines
- Use type hints for all function parameters and returns
- Maximum line length: 100 characters
- Use descriptive variable names
- Add docstrings to all public functions

**Example:**
```python
def download_google_trends_rss(
    geo: str = 'US',
    output_format: OutputFormat = 'dict'
) -> Union[List[Dict], str, 'pd.DataFrame']:
    """
    Download Google Trends RSS feed data.

    Args:
        geo: Country/region code (e.g., 'US', 'GB')
        output_format: Output format ('dict', 'json', 'csv', 'dataframe')

    Returns:
        Trend data in requested format

    Raises:
        InvalidParameterError: If parameters are invalid
    """
```

## Testing Guidelines

- Write tests for all new functionality
- Use pytest for testing
- Organize tests by module (test_rss_downloader.py, test_csv_downloader.py)
- Include both positive and negative test cases
- Test edge cases and error handling

**Test structure:**
```python
class TestFeature:
    """Test feature functionality"""

    def test_basic_functionality(self):
        """Test basic feature usage"""
        result = my_function()
        assert result is not None

    def test_error_handling(self):
        """Test error conditions"""
        with pytest.raises(InvalidParameterError):
            my_function(invalid_param)
```

## Documentation

- Keep README.md up to date
- Add docstrings to all public functions
- Include examples for new features
- Update CHANGELOG.md for all changes

## Questions?

If you have questions about contributing, feel free to:
- Open an issue with the question label
- Reach out via GitHub discussions

Thank you for contributing to trendspyg! 🚀
