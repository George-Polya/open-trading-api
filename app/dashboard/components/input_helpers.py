"""
Reusable Input Component Helpers.

Provides factory functions for common input patterns to reduce code
duplication and ensure consistent styling across dashboard components.
"""

import dash_bootstrap_components as dbc
from dash import html

from app.dashboard.constants import VALIDATION


def create_currency_input(
    input_id: str,
    label: str,
    value: float = 0,
    min_value: float = 0,
    step: float = 100,
    help_text: str | None = None,
    label_class: str = "small fw-bold",
    show_validation: bool = True,
) -> html.Div:
    """
    Create a currency input with $ prefix and optional validation feedback.

    Args:
        input_id: Unique ID for the input element.
        label: Label text to display above the input.
        value: Default value for the input.
        min_value: Minimum allowed value.
        step: Step increment for the input.
        help_text: Optional helper text below the input.
        label_class: CSS class for the label.
        show_validation: Whether to include validation feedback container.

    Returns:
        html.Div containing the labeled input with optional validation.
    """
    children = [
        dbc.Label(
            label,
            html_for=input_id,
            className=label_class,
        ),
        dbc.InputGroup(
            [
                dbc.InputGroupText("$"),
                dbc.Input(
                    id=input_id,
                    type="number",
                    value=value,
                    min=min_value,
                    step=step,
                ),
            ],
            size="sm",
        ),
    ]

    if show_validation:
        children.append(
            dbc.FormFeedback(
                id=f"feedback-{input_id}",
                type="invalid",
            )
        )

    if help_text:
        children.append(
            dbc.FormText(help_text, className="small text-muted")
        )

    return html.Div(children)


def create_percentage_input(
    input_id: str,
    label: str,
    value: float = 0,
    min_value: float = 0,
    max_value: float = 100,
    step: float = 0.01,
    help_text: str | None = None,
    label_class: str = "small",
    show_validation: bool = True,
) -> html.Div:
    """
    Create a percentage input with % suffix and optional validation feedback.

    Args:
        input_id: Unique ID for the input element.
        label: Label text to display above the input.
        value: Default value for the input.
        min_value: Minimum allowed value.
        max_value: Maximum allowed value.
        step: Step increment for the input.
        help_text: Optional helper text below the input.
        label_class: CSS class for the label.
        show_validation: Whether to include validation feedback container.

    Returns:
        html.Div containing the labeled input with optional validation.
    """
    children = [
        dbc.Label(
            label,
            html_for=input_id,
            className=label_class,
        ),
        dbc.InputGroup(
            [
                dbc.Input(
                    id=input_id,
                    type="number",
                    value=value,
                    min=min_value,
                    max=max_value,
                    step=step,
                ),
                dbc.InputGroupText("%"),
            ],
            size="sm",
        ),
    ]

    if show_validation:
        children.append(
            dbc.FormFeedback(
                id=f"feedback-{input_id}",
                type="invalid",
            )
        )

    if help_text:
        children.append(
            dbc.FormText(help_text, className="small text-muted")
        )

    return html.Div(children)


def create_select_with_label(
    select_id: str,
    label: str,
    options: list[dict],
    value: str,
    help_text: str | None = None,
    label_class: str = "small",
) -> html.Div:
    """
    Create a select dropdown with label and optional help text.

    Args:
        select_id: Unique ID for the select element.
        label: Label text to display above the select.
        options: List of option dicts with 'label' and 'value' keys.
        value: Default selected value.
        help_text: Optional helper text below the select.
        label_class: CSS class for the label.

    Returns:
        html.Div containing the labeled select.
    """
    children = [
        dbc.Label(
            label,
            html_for=select_id,
            className=label_class,
        ),
        dbc.Select(
            id=select_id,
            options=options,
            value=value,
            size="sm",
        ),
    ]

    if help_text:
        children.append(
            dbc.FormText(help_text, className="small text-muted")
        )

    return html.Div(children)


def create_text_input_with_label(
    input_id: str,
    label: str,
    value: str = "",
    placeholder: str = "",
    help_text: str | None = None,
    label_class: str = "small fw-bold",
    show_validation: bool = True,
) -> html.Div:
    """
    Create a text input with label and optional validation feedback.

    Args:
        input_id: Unique ID for the input element.
        label: Label text to display above the input.
        value: Default value for the input.
        placeholder: Placeholder text when input is empty.
        help_text: Optional helper text below the input.
        label_class: CSS class for the label.
        show_validation: Whether to include validation feedback container.

    Returns:
        html.Div containing the labeled input.
    """
    children = [
        dbc.Label(
            label,
            html_for=input_id,
            className=label_class,
        ),
        dbc.Input(
            id=input_id,
            type="text",
            value=value,
            placeholder=placeholder,
            size="sm",
        ),
    ]

    if show_validation:
        children.append(
            dbc.FormFeedback(
                id=f"feedback-{input_id}",
                type="invalid",
            )
        )

    if help_text:
        children.append(
            dbc.FormText(help_text, className="small text-muted")
        )

    return html.Div(children)


def create_card_header(title: str, icon_class: str) -> dbc.CardHeader:
    """
    Create a standardized card header with icon.

    Args:
        title: Title text for the header.
        icon_class: Font Awesome icon class (e.g., 'fas fa-cog').

    Returns:
        dbc.CardHeader with icon and title.
    """
    return dbc.CardHeader(
        [
            html.I(className=f"{icon_class} me-2"),
            title,
        ],
        className="fw-bold",
    )


def create_validation_alert(
    alert_id: str,
    default_message: str = "",
) -> dbc.Alert:
    """
    Create a validation alert container for displaying errors.

    Args:
        alert_id: Unique ID for the alert element.
        default_message: Default message (usually empty).

    Returns:
        dbc.Alert configured for validation messages.
    """
    return dbc.Alert(
        id=alert_id,
        is_open=False,
        color="danger",
        className="mb-2 py-2 small",
        children=default_message,
    )


def create_two_column_row(
    left_content: html.Div,
    right_content: html.Div,
    left_width: int = 6,
    right_width: int = 6,
    className: str = "",
) -> dbc.Row:
    """
    Create a two-column row layout.

    Args:
        left_content: Content for the left column.
        right_content: Content for the right column.
        left_width: Bootstrap column width for left (1-12).
        right_width: Bootstrap column width for right (1-12).
        className: Additional CSS class for the row.

    Returns:
        dbc.Row with two columns.
    """
    return dbc.Row(
        [
            dbc.Col(left_content, width=left_width),
            dbc.Col(right_content, width=right_width),
        ],
        className=className,
    )
