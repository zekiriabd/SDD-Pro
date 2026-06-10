using System.Collections.Generic;
using Microsoft.AspNetCore.Mvc;
using LegacyApi.Services;
using LegacyApi.Models;

namespace LegacyApi.Controllers
{
    [ApiController]
    [Route("api/orders")]
    public class OrdersController : ControllerBase
    {
        private readonly OrderService _service;

        public OrdersController(OrderService service)
        {
            _service = service;
        }

        [HttpGet]
        public IEnumerable<OrderDto> GetAll()
        {
            return _service.GetActiveOrders();
        }

        [HttpPost]
        public IActionResult Create(OrderDto dto)
        {
            int id = _service.PlaceOrder(dto);
            return CreatedAtAction(nameof(GetAll), new { id });
        }
    }
}
