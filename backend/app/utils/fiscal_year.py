MIN_FISCAL_YEAR = 2000
MAX_FISCAL_YEAR = 2100


class FiscalYearError(ValueError):
    pass


def parse_fiscal_year_arg(args, *, name='fiscal_year', required=False):
    raw_value = args.get(name)
    if raw_value in (None, ''):
        if required:
            raise FiscalYearError('Fiscal year is required.')
        return None

    try:
        fiscal_year = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise FiscalYearError('Fiscal year must be a number.') from exc

    validate_fiscal_year(fiscal_year)
    return fiscal_year


def validate_fiscal_year(fiscal_year):
    if not isinstance(fiscal_year, int) or fiscal_year < MIN_FISCAL_YEAR or fiscal_year > MAX_FISCAL_YEAR:
        raise FiscalYearError(f'Fiscal year must be between {MIN_FISCAL_YEAR} and {MAX_FISCAL_YEAR}.')
    return fiscal_year
