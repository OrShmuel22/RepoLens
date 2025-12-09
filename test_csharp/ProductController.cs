using Microsoft.AspNetCore.Mvc;
using MyApp.Services;
using MyApp.Models;

namespace MyApp.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class ProductController : ControllerBase
    {
        private readonly IProductService _productService;
        private readonly IInventoryService _inventoryService;
        private readonly ILogger<ProductController> _logger;

        public ProductController(
            IProductService productService, 
            IInventoryService inventoryService,
            ILogger<ProductController> logger)
        {
            _productService = productService;
            _inventoryService = inventoryService;
            _logger = logger;
        }

        [HttpGet]
        public async Task<IActionResult> GetAllProducts()
        {
            _logger.LogInformation("Fetching all products from database");
            var products = await _productService.GetAllProductsAsync();
            
            if (products == null || !products.Any())
            {
                return NotFound("No products available");
            }
            
            return Ok(products);
        }

        [HttpGet("{id}")]
        public async Task<IActionResult> GetProductById(int id)
        {
            if (id <= 0)
            {
                return BadRequest("Invalid product ID");
            }

            var product = await _productService.GetProductByIdAsync(id);
            
            if (product == null)
            {
                return NotFound($"Product with ID {id} not found");
            }

            return Ok(product);
        }

        [HttpPost]
        public async Task<IActionResult> CreateProduct([FromBody] CreateProductRequest request)
        {
            if (request == null)
            {
                return BadRequest("Product data is required");
            }

            // Validate that product name is unique
            var existingProduct = await _productService.GetProductByNameAsync(request.Name);
            if (existingProduct != null)
            {
                return Conflict("Product with this name already exists");
            }

            var productId = await _productService.CreateProductAsync(request);
            return CreatedAtAction(nameof(GetProductById), new { id = productId }, request);
        }

        [HttpPut("{id}")]
        public async Task<IActionResult> UpdateProduct(int id, [FromBody] UpdateProductRequest request)
        {
            if (id <= 0)
            {
                return BadRequest("Invalid product ID");
            }

            if (request == null)
            {
                return BadRequest("Product data is required");
            }

            var product = await _productService.GetProductByIdAsync(id);
            if (product == null)
            {
                return NotFound($"Product with ID {id} not found");
            }

            await _productService.UpdateProductAsync(id, request);
            return NoContent();
        }

        [HttpDelete("{id}")]
        public async Task<IActionResult> DeleteProduct(int id)
        {
            if (id <= 0)
            {
                return BadRequest("Invalid product ID");
            }

            var product = await _productService.GetProductByIdAsync(id);
            if (product == null)
            {
                return NotFound($"Product with ID {id} not found");
            }

            // Check inventory before deleting
            var inventoryCount = await _inventoryService.GetInventoryCountAsync(id);
            if (inventoryCount > 0)
            {
                return BadRequest("Cannot delete product with existing inventory");
            }

            await _productService.DeleteProductAsync(id);
            return NoContent();
        }

        [HttpGet("{id}/inventory")]
        public async Task<IActionResult> GetProductInventory(int id)
        {
            if (id <= 0)
            {
                return BadRequest("Invalid product ID");
            }

            var product = await _productService.GetProductByIdAsync(id);
            if (product == null)
            {
                return NotFound($"Product with ID {id} not found");
            }

            var inventory = await _inventoryService.GetInventoryByProductIdAsync(id);
            return Ok(new { ProductId = id, Inventory = inventory });
        }
    }
}
