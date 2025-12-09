using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Authorization;
using System.Threading.Tasks;
using System.Collections.Generic;
using DemoApp.Services;
using DemoApp.Models;

namespace DemoApp.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    [Authorize]
    public class OrdersController : ControllerBase
    {
        private readonly IOrderService _orderService;
        private readonly ILogger<OrdersController> _logger;

        public OrdersController(IOrderService orderService, ILogger<OrdersController> logger)
        {
            _orderService = orderService;
            _logger = logger;
        }

        [HttpPost]
        public async Task<IActionResult> CreateOrder([FromBody] CreateOrderRequest request)
        {
            var userId = User.FindFirst("sub")?.Value;
            
            if (request.Items == null || request.Items.Count == 0)
            {
                return BadRequest("Order must contain at least one item");
            }

            try
            {
                var order = await _orderService.CreateOrderAsync(userId, request.Items);
                return CreatedAtAction(nameof(GetOrder), new { id = order.Id }, order);
            }
            catch (InvalidOperationException ex)
            {
                return BadRequest(new { message = ex.Message });
            }
        }

        [HttpGet("{id}")]
        public async Task<IActionResult> GetOrder(int id)
        {
            var order = await _orderService.GetOrderByIdAsync(id);
            
            if (order == null)
            {
                return NotFound();
            }

            // Check if user owns this order
            var userId = User.FindFirst("sub")?.Value;
            if (order.UserId != userId && !User.IsInRole("Admin"))
            {
                return Forbid();
            }

            return Ok(order);
        }

        [HttpGet]
        public async Task<IActionResult> GetMyOrders()
        {
            var userId = User.FindFirst("sub")?.Value;
            var orders = await _orderService.GetUserOrdersAsync(userId);
            
            return Ok(orders);
        }

        [HttpDelete("{id}")]
        public async Task<IActionResult> CancelOrder(int id)
        {
            var order = await _orderService.GetOrderByIdAsync(id);
            
            if (order == null)
            {
                return NotFound();
            }

            // Check ownership
            var userId = User.FindFirst("sub")?.Value;
            if (order.UserId != userId)
            {
                return Forbid();
            }

            var cancelled = await _orderService.CancelOrderAsync(id);
            
            if (!cancelled)
            {
                return BadRequest("Cannot cancel order");
            }

            return NoContent();
        }
    }
}
