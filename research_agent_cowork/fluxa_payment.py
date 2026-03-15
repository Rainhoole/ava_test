#!/usr/bin/env python3
"""
Fluxa Payment Service for Research Agent.

Handles payment operations using the Fluxa Wallet API:
- Create intent mandates for user authorization
- Process payments using x402 v3 protocol
- Create payment links for collecting fees
"""

import os
import httpx
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Fluxa API endpoints
FLUXA_WALLET_API = "https://walletapi.fluxapay.xyz"
FLUXA_AGENT_ID_API = "https://agentid.fluxapay.xyz"

# USDC contract on Base network
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PaymentResult:
    """Result of a payment operation."""
    success: bool
    status: PaymentStatus
    transaction_hash: Optional[str] = None
    amount_usd: Optional[float] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class MandateResult:
    """Result of mandate creation."""
    success: bool
    mandate_id: Optional[str] = None
    authorization_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PaymentLinkResult:
    """Result of payment link creation."""
    success: bool
    link_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class FluxaPaymentService:
    """
    Service for handling Fluxa payments.

    Usage:
        service = FluxaPaymentService()

        # Create payment link for a completed task
        result = await service.create_payment_link(
            amount_usd=1.50,
            description="Research task payment",
            task_id="xxx"
        )

        # Process payment with mandate
        payment = await service.process_payment(
            mandate_id="mandate_xxx",
            amount_usd=1.50,
            description="Research task payment"
        )
    """

    def __init__(self):
        self.agent_jwt = os.environ.get("FLUXA_AGENT_JWT")
        self.agent_id = os.environ.get("FLUXA_AGENT_ID")
        self.agent_token = os.environ.get("FLUXA_AGENT_TOKEN")
        self.pay_to_address = os.environ.get("FLUXA_PAY_TO_ADDRESS")
        self.network = os.environ.get("FLUXA_NETWORK", "base")

        if not self.agent_jwt:
            logger.warning("FLUXA_AGENT_JWT not set - payment features will be limited")
        if not self.pay_to_address:
            logger.warning("FLUXA_PAY_TO_ADDRESS not set - cannot receive payments")
        if not self.agent_token:
            logger.warning("FLUXA_AGENT_TOKEN not set - cannot refresh JWT when expired")

    def _get_headers(self, include_auth: bool = True) -> Dict[str, str]:
        """Get request headers with optional authorization."""
        headers = {"Content-Type": "application/json"}
        if include_auth and self.agent_jwt:
            headers["Authorization"] = f"Bearer {self.agent_jwt}"
        return headers

    async def refresh_jwt(self) -> bool:
        """
        Refresh the JWT token using agent_id and token.

        Returns:
            True if refresh was successful, False otherwise.
        """
        if not self.agent_id or not self.agent_token:
            logger.error("Cannot refresh JWT: FLUXA_AGENT_ID or FLUXA_AGENT_TOKEN not set")
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{FLUXA_AGENT_ID_API}/refresh",
                    headers={"Content-Type": "application/json"},
                    json={
                        "agent_id": self.agent_id,
                        "token": self.agent_token
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    new_jwt = data.get("jwt")
                    if new_jwt:
                        self.agent_jwt = new_jwt
                        # Also update the environment variable for persistence
                        os.environ["FLUXA_AGENT_JWT"] = new_jwt
                        logger.info("Successfully refreshed Fluxa JWT token")
                        return True
                    else:
                        logger.error("JWT refresh response missing 'jwt' field")
                        return False
                else:
                    logger.error(f"Failed to refresh JWT: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error refreshing JWT: {str(e)}")
            return False

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        payload: Dict[str, Any],
        timeout: float = 30.0
    ) -> httpx.Response:
        """
        Make an HTTP request with automatic JWT refresh on 401 errors.

        Args:
            method: HTTP method (POST, GET, etc.)
            url: Request URL
            payload: JSON payload
            timeout: Request timeout in seconds

        Returns:
            httpx.Response object
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            # First attempt
            response = await client.request(
                method,
                url,
                headers=self._get_headers(),
                json=payload
            )

            # If unauthorized, try to refresh JWT and retry
            if response.status_code == 401:
                logger.info("Received 401, attempting to refresh JWT...")
                if await self.refresh_jwt():
                    # Retry with new JWT
                    response = await client.request(
                        method,
                        url,
                        headers=self._get_headers(),
                        json=payload
                    )

            return response

    def _usd_to_atomic(self, usd_amount: float) -> str:
        """Convert USD amount to USDC atomic units (6 decimals)."""
        # USDC has 6 decimals, so 1 USDC = 1,000,000 atomic units
        atomic = int(usd_amount * 1_000_000)
        return str(atomic)

    def _atomic_to_usd(self, atomic_units: str) -> float:
        """Convert USDC atomic units to USD amount."""
        return int(atomic_units) / 1_000_000

    async def create_intent_mandate(
        self,
        budget_usd: float,
        valid_days: int = 30,
        category: str = "research_data",
        description: Optional[str] = None
    ) -> MandateResult:
        """
        Create an intent mandate for user authorization.

        The user must sign this mandate in the Fluxa Wallet UI before
        payments can be processed.

        Args:
            budget_usd: Maximum amount the user is willing to spend
            valid_days: Number of days the mandate is valid
            category: Category of the intent
            description: Human-readable description

        Returns:
            MandateResult with mandate_id and authorization_url
        """
        if description is None:
            description = f"Research agent budget of ${budget_usd:.2f} USDC valid for {valid_days} days"

        valid_seconds = valid_days * 24 * 60 * 60
        limit_amount = self._usd_to_atomic(budget_usd)

        payload = {
            "intent": {
                "naturalLanguage": description,
                "category": category,
                "currency": "USDC",
                "limitAmount": limit_amount,
                "validForSeconds": valid_seconds,
                "hostAllowlist": []
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{FLUXA_WALLET_API}/api/mandates/create-intent",
                    headers=self._get_headers(include_auth=bool(self.agent_jwt)),
                    json=payload
                )

                if response.status_code == 200 or response.status_code == 201:
                    data = response.json()
                    return MandateResult(
                        success=True,
                        mandate_id=data.get("mandateId"),
                        authorization_url=data.get("authorizationUrl")
                    )
                else:
                    error_msg = f"Failed to create mandate: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return MandateResult(success=False, error=error_msg)

        except Exception as e:
            error_msg = f"Error creating mandate: {str(e)}"
            logger.error(error_msg)
            return MandateResult(success=False, error=error_msg)

    async def process_payment(
        self,
        mandate_id: str,
        amount_usd: float,
        description: str,
        task_id: str = "research-task",
        user_jwt: Optional[str] = None
    ) -> PaymentResult:
        """
        Process a payment using the x402 protocol with payment links.

        Flow:
        1. Create payment link with specific amount (using backend JWT)
        2. GET the link to get 402 response with payment params
        3. Call x402V3Payment with mandate_id + payment params (using user JWT)
        4. Re-request payment link with X-Payment header

        Args:
            mandate_id: The authorized mandate ID from frontend
            amount_usd: Amount to charge in USD
            description: Payment description
            task_id: Task identifier for tracking
            user_jwt: JWT from frontend agent that created the mandate

        Returns:
            PaymentResult with transaction details
        """
        if not self.agent_jwt:
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error="FLUXA_AGENT_JWT not configured"
            )

        # Use user_jwt for x402 payment, fallback to backend JWT
        x402_jwt = user_jwt or self.agent_jwt
        if not x402_jwt:
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error="No JWT available for x402 payment"
            )

        if not self.pay_to_address:
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error="FLUXA_PAY_TO_ADDRESS not configured"
            )

        # Step 1: Create payment link
        link_result = await self.create_payment_link(
            amount_usd=amount_usd,
            description=description,
            task_id=task_id
        )

        if not link_result.success or not link_result.url:
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error=f"Failed to create payment link: {link_result.error}"
            )

        payment_link_url = link_result.url
        logger.info(f"[PAY] Step 1 OK - Created payment link: {payment_link_url}")
        logger.info(f"[PAY] Link ID: {link_result.link_id}")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Step 2: GET payment link to get 402 response
                logger.info(f"[PAY] Step 2 - GET payment link for 402 response...")
                response_402 = await client.get(payment_link_url)
                logger.info(f"[PAY] Step 2 - Response status: {response_402.status_code}")

                if response_402.status_code != 402:
                    logger.error(f"[PAY] Step 2 FAILED - Expected 402, got {response_402.status_code}")
                    logger.error(f"[PAY] Response body: {response_402.text[:500]}")
                    return PaymentResult(
                        success=False,
                        status=PaymentStatus.FAILED,
                        error=f"Expected 402, got {response_402.status_code}: {response_402.text}"
                    )

                # Parse 402 response to get payment requirements
                payment_required = response_402.json()
                accepts = payment_required.get("accepts", [])
                logger.info(f"[PAY] Step 2 OK - Got {len(accepts)} payment options")

                if not accepts:
                    logger.error(f"[PAY] Step 2 FAILED - No accepts in response: {payment_required}")
                    return PaymentResult(
                        success=False,
                        status=PaymentStatus.FAILED,
                        error="No payment options in 402 response"
                    )

                accept = accepts[0]
                logger.info(f"[PAY] Step 2 - Payment requirements: amount={accept.get('maxAmountRequired')}, payTo={accept.get('payTo')}")

                # Step 3: Call x402V3Payment with mandate_id + payment params
                resource_path = accept.get("resource", f"/paymentlink/{link_result.link_id}")
                full_resource = f"{FLUXA_WALLET_API}{resource_path}"

                x402_payload = {
                    "mandateId": mandate_id,
                    "scheme": accept.get("scheme", "exact"),
                    "network": self.network,
                    "amount": accept.get("maxAmountRequired"),
                    "currency": "USDC",
                    "assetAddress": accept.get("asset", USDC_ADDRESS),
                    "payTo": accept.get("payTo", self.pay_to_address),
                    "host": "walletapi.fluxapay.xyz",
                    "resource": full_resource,
                    "description": description,
                    "tokenName": accept.get("extra", {}).get("name", "USD Coin"),
                    "tokenVersion": accept.get("extra", {}).get("version", "2"),
                    "validityWindowSeconds": accept.get("maxTimeoutSeconds", 60)
                }

                logger.info(f"[PAY] Step 3 - Calling x402V3Payment...")
                logger.info(f"[PAY] Step 3 - mandate_id: {mandate_id}")
                logger.info(f"[PAY] Step 3 - amount: {x402_payload['amount']}, payTo: {x402_payload['payTo']}")
                logger.info(f"[PAY] Step 3 - resource: {x402_payload['resource']}")
                logger.info(f"[PAY] Step 3 - Using JWT: {x402_jwt[:20]}...{x402_jwt[-10:]}" if x402_jwt else "[PAY] Step 3 - JWT is None!")

                # Use user's JWT for x402 payment (mandate belongs to user's agent)
                x402_response = await client.post(
                    f"{FLUXA_WALLET_API}/api/payment/x402V3Payment",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {x402_jwt}"
                    },
                    json=x402_payload,
                    timeout=60.0
                )

                logger.info(f"[PAY] Step 3 - Response status: {x402_response.status_code}")
                x402_data = x402_response.json()
                logger.info(f"[PAY] Step 3 - Response keys: {list(x402_data.keys())}")

                if x402_response.status_code != 200:
                    error_msg = x402_data.get("error") or x402_data.get("message") or f"x402 payment failed: {x402_response.status_code}"
                    logger.error(f"[PAY] Step 3 FAILED: {error_msg}")
                    logger.error(f"[PAY] Step 3 - Full response: {x402_data}")
                    return PaymentResult(
                        success=False,
                        status=PaymentStatus.FAILED,
                        error=error_msg,
                        details=x402_data
                    )

                # Get X-Payment header from response (use xPaymentB64 which is already base64 encoded)
                x_payment = x402_data.get("xPaymentB64")
                logger.info(f"[PAY] Step 3 OK - status: {x402_data.get('status')}, has xPaymentB64: {bool(x_payment)}")

                if not x_payment:
                    logger.error(f"[PAY] Step 3 FAILED - No xPaymentB64 in response")
                    logger.error(f"[PAY] Step 3 - Full response: {x402_data}")
                    return PaymentResult(
                        success=False,
                        status=PaymentStatus.FAILED,
                        error="No xPaymentB64 in x402 response",
                        details=x402_data
                    )

                logger.info(f"[PAY] Step 4 - Completing payment with X-Payment header...")
                logger.info(f"[PAY] Step 4 - X-Payment length: {len(x_payment)}")

                # Step 4: Re-request payment link with X-Payment header
                final_response = await client.get(
                    payment_link_url,
                    headers={"X-Payment": x_payment}
                )

                logger.info(f"[PAY] Step 4 - Response status: {final_response.status_code}")
                final_data = final_response.json()
                logger.info(f"[PAY] Step 4 - Response: {final_data}")

                if final_response.status_code == 200 and final_data.get("status") == "success":
                    receipt = final_data.get("receipt", {})
                    tx_hash = receipt.get("txHash")
                    logger.info(f"[PAY] Step 4 OK - Payment SUCCESS! txHash: {tx_hash}")
                    return PaymentResult(
                        success=True,
                        status=PaymentStatus.COMPLETED,
                        transaction_hash=tx_hash,
                        amount_usd=amount_usd,
                        details=final_data
                    )
                else:
                    error_msg = final_data.get("error") or final_data.get("reason") or f"Final payment failed: {final_response.status_code}"
                    logger.error(f"[PAY] Step 4 FAILED: {error_msg}")
                    logger.error(f"[PAY] Step 4 - Full response: {final_data}")
                    return PaymentResult(
                        success=False,
                        status=PaymentStatus.FAILED,
                        error=error_msg,
                        details=final_data
                    )

        except Exception as e:
            error_msg = f"Error processing payment: {str(e)}"
            logger.error(error_msg)
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error=error_msg
            )

    async def create_payment_link(
        self,
        amount_usd: float,
        description: str,
        task_id: str,
        expires_hours: int = 24,
        max_uses: int = 1
    ) -> PaymentLinkResult:
        """
        Create a payment link for collecting fees.

        This is used when the backend needs to charge for a completed task.

        Args:
            amount_usd: Amount to charge in USD
            description: Payment description
            task_id: Associated task ID
            expires_hours: Hours until link expires
            max_uses: Maximum number of times the link can be used

        Returns:
            PaymentLinkResult with link URL
        """
        if not self.agent_jwt:
            return PaymentLinkResult(
                success=False,
                error="FLUXA_AGENT_JWT not configured"
            )

        amount_atomic = self._usd_to_atomic(amount_usd)

        # Calculate expiration time
        from datetime import datetime, timedelta
        expires_at = (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat() + "Z"

        # Resource content includes task details
        resource_content = {
            "task_id": task_id,
            "service": "research_agent",
            "message": "Thank you for using AVA Research Agent!"
        }

        payload = {
            "amount": amount_atomic,
            "currency": "USDC",
            "network": self.network,
            "description": description,
            "resourceContent": str(resource_content),
            "expiresAt": expires_at,
            "maxUses": max_uses
        }

        try:
            response = await self._request_with_retry(
                "POST",
                f"{FLUXA_WALLET_API}/api/payment-links",
                payload,
                timeout=30.0
            )

            if response.status_code == 201 or response.status_code == 200:
                data = response.json()
                payment_link = data.get("paymentLink", {})
                return PaymentLinkResult(
                    success=True,
                    link_id=payment_link.get("linkId"),
                    url=payment_link.get("url")
                )
            else:
                error_msg = f"Failed to create payment link: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return PaymentLinkResult(success=False, error=error_msg)

        except Exception as e:
            error_msg = f"Error creating payment link: {str(e)}"
            logger.error(error_msg)
            return PaymentLinkResult(success=False, error=error_msg)

    def calculate_task_cost(
        self,
        claude_cost_usd: float,
        tool_calls: int,
        tool_call_rate: float = 0.01
    ) -> Dict[str, float]:
        """
        Calculate the total cost for a research task.

        Args:
            claude_cost_usd: Cost from Claude API usage
            tool_calls: Number of tool calls made
            tool_call_rate: Cost per tool call (default $0.01)

        Returns:
            Dict with cost breakdown
        """
        tool_cost = tool_calls * tool_call_rate
        total_cost = claude_cost_usd + tool_cost

        return {
            "claude_cost_usd": round(claude_cost_usd, 6),
            "tool_calls": tool_calls,
            "tool_call_rate": tool_call_rate,
            "tool_cost_usd": round(tool_cost, 6),
            "total_cost_usd": round(total_cost, 6)
        }


# Singleton instance
_payment_service: Optional[FluxaPaymentService] = None


def get_payment_service() -> FluxaPaymentService:
    """Get or create the payment service singleton."""
    global _payment_service
    if _payment_service is None:
        _payment_service = FluxaPaymentService()
    return _payment_service
